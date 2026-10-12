#!/usr/bin/env python3
"""Runs on the machine under test. Drives llama-server through plan.json and logs what happened.

Writes to --out:
  events.jsonl   one JSON object per event (idle segments, cache fills, decode requests, cell start/end)
  hwmon.csv      10 Hz package power, temperatures, clock, GPU busy
  guard.jsonl    every 5 s: models loaded in ollama, busy processes
  meta.json      machine and software snapshot

The wall power comes from a second process on another machine (sample_plug.py). Both use unix time;
the machines are NTP-synced and the offset is checked in analysis.
"""
import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
import urllib.request

PORT = 8099
CTX = 36864
DECODE_N = 512
WINDOW_S = 120.0
SETTLE_S = 30.0
LICENCES = "/usr/share/common-licenses"


def now() -> float:
    return time.time()


class Log:
    def __init__(self, path: pathlib.Path):
        self.f = open(path, "a", buffering=1)
        self.lock = threading.Lock()

    def write(self, **kw):
        kw.setdefault("t", now())
        with self.lock:
            self.f.write(json.dumps(kw) + "\n")


def find_hwmon(name: str) -> str:
    for h in sorted(pathlib.Path("/sys/class/hwmon").glob("hwmon*")):
        if (h / "name").read_text().strip() == name:
            return str(h)
    raise SystemExit(f"no hwmon named {name}")


def read_int(path: str, default=None):
    try:
        return int(pathlib.Path(path).read_text().strip())
    except Exception:
        return default


class HwmonSampler(threading.Thread):
    def __init__(self, path: pathlib.Path, hz: float = 10.0):
        super().__init__(daemon=True)
        self.amd = find_hwmon("amdgpu")
        self.cpu = find_hwmon("k10temp")
        self.f = open(path, "w", buffering=1 << 16)
        self.f.write("t_unix,ppt_w,gpu_temp_c,cpu_temp_c,gpu_clock_mhz,gpu_busy_pct\n")
        self.period = 1.0 / hz
        self.stop = threading.Event()

    def run(self):
        nxt = time.monotonic()
        last_flush = time.monotonic()
        while not self.stop.is_set():
            t = now()
            ppt = read_int(self.amd + "/power1_input")
            gt = read_int(self.amd + "/temp1_input")
            ct = read_int(self.cpu + "/temp1_input")
            fr = read_int(self.amd + "/freq1_input")
            busy = read_int("/sys/class/drm/card0/device/gpu_busy_percent")
            self.f.write(
                f"{t:.3f},{'' if ppt is None else ppt / 1e6:.3f},{'' if gt is None else gt / 1e3:.1f},"
                f"{'' if ct is None else ct / 1e3:.1f},{'' if fr is None else fr / 1e6:.0f},{'' if busy is None else busy}\n"
            )
            if time.monotonic() - last_flush > 5:
                self.f.flush()
                last_flush = time.monotonic()
            nxt += self.period
            time.sleep(max(0.0, nxt - time.monotonic()))
        self.f.flush()


ALLOWED_COMM = {"llama-server", "python3", "sshd", "sshd-session", "ssh", "bash", "sh", "systemd", "kworker", "ps", "cat", "sleep"}


def proc_cpu_ticks() -> dict:
    out = {}
    for p in pathlib.Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            stat = (p / "stat").read_text()
            comm = stat[stat.index("(") + 1: stat.rindex(")")]
            rest = stat[stat.rindex(")") + 2:].split()
            out[int(p.name)] = (comm, int(rest[11]) + int(rest[12]))
        except Exception:
            continue
    return out


class Guard(threading.Thread):
    """Every 5 s: note any ollama model loaded and any foreign process above 10% of a core."""

    def __init__(self, log: Log):
        super().__init__(daemon=True)
        self.log = log
        self.stop = threading.Event()
        self.flags = []  # (t, description)
        self.lock = threading.Lock()
        self.hz = os.sysconf("SC_CLK_TCK")

    def take_flags(self, since: float):
        with self.lock:
            return [f for f in self.flags if f[0] >= since]

    def run(self):
        prev = proc_cpu_ticks()
        tprev = time.monotonic()
        while not self.stop.wait(5.0):
            cur = proc_cpu_ticks()
            dt = time.monotonic() - tprev
            tprev = time.monotonic()
            busy = []
            for pid, (comm, ticks) in cur.items():
                if pid in prev and comm not in ALLOWED_COMM and not comm.startswith("kworker"):
                    pct = 100.0 * (ticks - prev[pid][1]) / self.hz / dt
                    if pct > 10:
                        busy.append({"pid": pid, "comm": comm, "cpu_pct": round(pct, 1)})
            prev = cur
            models = []
            try:
                with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=2) as r:
                    models = [m.get("name") for m in json.load(r).get("models", [])]
            except Exception:
                pass
            self.log.write(kind="guard", ollama_models=models, busy=busy)
            if busy:
                with self.lock:
                    self.flags.append((now(), {"busy": busy}))


def ollama_requests(t0: float, t1: float) -> int:
    """Generation, chat or embedding requests that ollama served in [t0, t1], from its journal."""
    try:
        out = subprocess.run(["journalctl", "-u", "ollama", "--since", f"@{int(t0)}", "--until", f"@{int(t1) + 1}", "--no-pager"],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return -1
    return sum(1 for line in out.splitlines() if "POST" in line and any(k in line for k in ('/api/generate', '/api/chat', '/api/embed', '/v1/')))


def http_json(method: str, url: str, body=None, timeout: float = 3600):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


class Server:
    def __init__(self, build: str, model: str, logdir: pathlib.Path, tag: str):
        self.build = build
        self.model = model
        self.logfile = open(logdir / f"server-{tag}.log", "w")
        self.proc = None

    def start(self):
        env = dict(os.environ, LD_LIBRARY_PATH=self.build)
        cmd = [f"{self.build}/llama-server", "-m", self.model, "-ngl", "99", "-c", str(CTX), "-np", "1", "-fa", "on",
               "--no-context-shift", "--host", "127.0.0.1", "--port", str(PORT), "--no-webui"]
        self.proc = subprocess.Popen(cmd, env=env, stdout=self.logfile, stderr=subprocess.STDOUT)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 900:
            if self.proc.poll() is not None:
                raise RuntimeError(f"llama-server exited with {self.proc.returncode}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
                    if json.load(r).get("status") == "ok":
                        return time.monotonic() - t0
            except Exception:
                pass
            time.sleep(1.0)
        raise RuntimeError("llama-server did not become healthy in 900 s")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.logfile.close()


def licence_text() -> str:
    parts = []
    for p in sorted(pathlib.Path(LICENCES).iterdir()):
        if p.is_file() and not p.is_symlink():
            parts.append(p.read_text(errors="ignore"))
    return "\n\n".join(parts)


class CellFailed(Exception):
    """The server rejected or dropped a request. The cell is logged as failed and the server is restarted."""


def completion(ids, n_predict):
    body = {"prompt": ids, "n_predict": n_predict, "temperature": 0, "ignore_eos": True, "cache_prompt": True,
            "stream": False}
    t_send = now()
    try:
        r = http_json("POST", f"http://127.0.0.1:{PORT}/completion", body)
    except Exception as e:
        raise CellFailed(f"{type(e).__name__}: {e}") from e
    t_recv = now()
    tm = r.get("timings", {})
    keep = {k: tm.get(k) for k in ("prompt_n", "prompt_ms", "predicted_n", "predicted_ms", "predicted_per_second", "cache_n")}
    return t_send, t_recv, keep, r.get("tokens_predicted"), r.get("tokens_cached")


TICK_PERIOD_S = 600.0   # another host sends a tiny ollama request at about :00, :10, :20 ... every hour
TICK_OFFSET_S = 3.5
TICK_GUARD_S = 12.0
EST_CELL_S = {64: 230.0, 4096: 240.0, 16384: 300.0, 32768: 380.0}   # fill + settles + window, with margin


def slot_wait(t: float, est_s: float, period: float = TICK_PERIOD_S, offset: float = TICK_OFFSET_S,
              guard: float = TICK_GUARD_S) -> float:
    """Seconds to wait so that a cell of est_s seconds ends before the next periodic foreign request."""
    nxt = (int((t - offset) // period) + 1) * period + offset
    if nxt - t >= est_s + 20:
        return 0.0
    return nxt + guard - t


def idle(log: Log, label: str, seconds: float, **kw):
    t0 = now()
    time.sleep(seconds)
    log.write(kind="idle", label=label, t0=t0, t1=now(), **kw)


def run_cell(log, guard, ids, model_key, depth, rnd, window_s, settle_s):
    try:
        return _run_cell(log, guard, ids, model_key, depth, rnd, window_s, settle_s)
    except CellFailed as e:
        log.write(kind="cell_failed", error=str(e), model=model_key, depth=depth, round=rnd)
        raise


def _run_cell(log, guard, ids, model_key, depth, rnd, window_s, settle_s):
    cell = {"model": model_key, "depth": depth, "round": rnd}
    wait = slot_wait(now(), EST_CELL_S.get(depth, 380.0) * (window_s / WINDOW_S if window_s < WINDOW_S else 1.0))
    if wait > 0:
        idle(log, "wait_for_gap", wait, **cell)
    t_cell = now()
    log.write(kind="cell_start", **cell)
    t0, t1, tm, _, cached = completion(ids[:depth], 1)
    log.write(kind="fill", t0=t0, t1=t1, timings=tm, tokens_cached=cached, **cell)
    t0, t1, tm, _, _ = completion(ids[:depth], 64)
    reuse = (tm.get("prompt_n") or 0) <= 8
    log.write(kind="probe", t0=t0, t1=t1, timings=tm, cache_reused=reuse, **cell)
    tok_s = tm.get("predicted_per_second") or 20.0
    idle(log, "settle_before", settle_s, **cell)
    reqs = []
    t_win0 = now()
    if reuse:
        while True:
            t_send, t_recv, tm, _, _ = completion(ids[:depth], DECODE_N)
            reqs.append({"t_send": t_send, "t_recv": t_recv, "timings": tm})
            log.write(kind="decode_request", t_send=t_send, t_recv=t_recv, timings=tm, **cell)
            if t_recv - t_win0 >= window_s and len(reqs) >= 3:
                break
    else:
        n = int(max(DECODE_N, min(8000, window_s * 0.85 * tok_s)))
        t_send, t_recv, tm, _, _ = completion(ids[:depth], n)
        reqs.append({"t_send": t_send, "t_recv": t_recv, "timings": tm})
        log.write(kind="decode_request", t_send=t_send, t_recv=t_recv, timings=tm, **cell)
    t_win1 = now()
    log.write(kind="window", t0=reqs[0]["t_send"], t1=reqs[-1]["t_recv"], n_requests=len(reqs), cache_reused=reuse,
              tokens=sum(r["timings"].get("predicted_n") or 0 for r in reqs), **cell)
    idle(log, "settle_after", settle_s, **cell)
    flags = guard.take_flags(t_cell)
    n_oll = ollama_requests(t_cell, now())
    if n_oll != 0:
        flags.append((now(), {"ollama_requests": n_oll}))
    log.write(kind="cell_end", contaminated=bool(flags), flags=flags[:5], ollama_requests=n_oll, **cell)
    return bool(flags)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(args, models, out: pathlib.Path):
    def sh(cmd):
        try:
            return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60).stdout.strip()
        except Exception as e:
            return f"error: {e}"
    meta = {
        "started_unix": now(),
        "uname": sh("uname -a"),
        "cmdline": sh("cat /proc/cmdline"),
        "governor": sh("cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
        "mesa": sh("vulkaninfo --summary 2>/dev/null | grep -iE 'driverInfo|deviceName' | head -3"),
        "build": args.build,
        "build_files": sh(f"ls {args.build} | head -40"),
        "os": sh("grep PRETTY /etc/os-release"),
        "mem_gb": sh("free -g | sed -n 2p"),
        "models": {},
    }
    for key, m in models.items():
        p = f"{args.models_dir}/{m['file']}"
        meta["models"][key] = {"file": m["file"], "bytes": os.path.getsize(p), "sha256": sha256_file(p)}
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--build", required=True)
    ap.add_argument("--models-dir", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--models", required=True)
    ap.add_argument("--window", type=float, default=WINDOW_S)
    ap.add_argument("--settle", type=float, default=SETTLE_S)
    ap.add_argument("--bare-idle", type=float, default=300.0)
    ap.add_argument("--block-idle", type=float, default=120.0)
    ap.add_argument("--only-rounds", type=int, default=0, help="smoke tests: run only this many rounds")
    ap.add_argument("--only-models", default="", help="smoke tests: comma list of model keys")
    ap.add_argument("--only-depths", default="", help="smoke tests: comma list of depths")
    ap.add_argument("--cells-file", default="", help="JSON list of [round, model, depth]: run only these cells, in plan order")
    ap.add_argument("--no-hash", action="store_true")
    ap.add_argument("--no-step", action="store_true")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    plan = json.loads(pathlib.Path(args.plan).read_text())
    models = json.loads(pathlib.Path(args.models).read_text())
    log = Log(out / "events.jsonl")
    if args.no_hash:
        (out / "meta.json").write_text(json.dumps({"note": "smoke test, no hashes", "build": args.build}))
    else:
        snapshot(args, models, out)
        time.sleep(120)  # let the machine cool after reading ~95 GB of model files
    hw = HwmonSampler(out / "hwmon.csv")
    guard = Guard(log)
    hw.start()
    guard.start()
    try:
        idle(log, "bare_idle_start", args.bare_idle)
        text = licence_text()
        only_models = set(filter(None, args.only_models.split(",")))
        only_depths = {int(x) for x in filter(None, args.only_depths.split(","))}
        contaminated = []

        wanted = None
        if args.cells_file:
            wanted = {tuple(c) for c in json.loads(pathlib.Path(args.cells_file).read_text())}
        failed = []

        def run_block(model_key, depths, rnd, step=False):
            m = models[model_key]
            path = f"{args.models_dir}/{m['file']}"
            tag = f"r{rnd}-{model_key}"
            srv = Server(args.build, path, out, tag)
            t_load = srv.start()
            log.write(kind="server_up", model=model_key, round=rnd, load_s=t_load)
            try:
                ids = http_json("POST", f"http://127.0.0.1:{PORT}/tokenize", {"content": text, "add_special": True})["tokens"]
                if len(ids) < max(plan["depths"]) + 1:
                    raise RuntimeError(f"prompt text has only {len(ids)} tokens")
                log.write(kind="tokenized", model=model_key, n_tokens=len(ids))
                idle(log, "loaded_idle", 60 if not args.no_hash else 15, model=model_key, round=rnd)
                if step:
                    run_step(log, ids, model_key, args)
                    depths = []
                for d in depths:
                    if only_depths and d not in only_depths:
                        continue
                    if wanted is not None and (rnd, model_key, d) not in wanted:
                        continue
                    try:
                        if run_cell(log, guard, ids, model_key, d, rnd, args.window, args.settle):
                            contaminated.append((model_key, d, rnd))
                    except CellFailed:
                        failed.append((model_key, d, rnd))
                        srv.stop()
                        srv = Server(args.build, path, out, f"{tag}-restart{len(failed)}")
                        t_load = srv.start()
                        log.write(kind="server_up", model=model_key, round=rnd, load_s=t_load, restart=True)
                        idle(log, "loaded_idle", 60, model=model_key, round=rnd)
            finally:
                srv.stop()
            idle(log, "bare_idle_block", args.block_idle, model=model_key, round=rnd)

        if not args.no_step:
            run_block(next(iter(models)), [], 0, step=True)
        for rd in plan["rounds"]:
            if args.only_rounds and rd["round"] > args.only_rounds:
                break
            for b in rd["blocks"]:
                if only_models and b["model"] not in only_models:
                    continue
                if wanted is not None and not any((rd["round"], b["model"], d) in wanted for d in b["depths"]):
                    continue
                run_block(b["model"], b["depths"], rd["round"])
        for (mk, d, rnd) in contaminated[:] + failed[:]:
            log.write(kind="rerun_contaminated", model=mk, depth=d, round=rnd)
            wanted = None
            run_block(mk, [d], rnd)
        idle(log, "bare_idle_end", args.bare_idle)
        log.write(kind="done")
    finally:
        guard.stop.set()
        hw.stop.set()
        time.sleep(0.5)


def run_step(log, ids, model_key, args):
    """Load step for estimating the smart plug's response lag: 60 s idle, 60 s decode, 60 s idle."""
    d = 64
    completion(ids[:d], 1)
    idle(log, "step_idle_before", 60, model=model_key)
    t0 = now()
    while now() - t0 < 60:
        completion(ids[:d], DECODE_N)
    log.write(kind="step_load", t0=t0, t1=now(), model=model_key)
    idle(log, "step_idle_after", 60, model=model_key)


if __name__ == "__main__":
    sys.exit(main())
