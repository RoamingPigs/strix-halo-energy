#!/usr/bin/env python3
"""Before the measured run: check the machine and the repository are in the state the plan says. Exit 1 on any failure.
usage: preflight.py <expected kernel> <plan file in this repository>   (needs ssh warden, TASMOTA_PASSWORD_WARDEN)"""
import json
import os
import subprocess
import sys
import time
import urllib.request

KERNEL, PLAN = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
bad = 0


def sh(cmd, remote=False):
    argv = ["ssh", "warden", "bash", "-s"] if remote else ["bash", "-c", cmd]
    r = subprocess.run(argv, input=cmd if remote else None, capture_output=True, text=True, timeout=120)
    return r.returncode, (r.stdout + r.stderr).strip()


def check(name, ok, detail=""):
    global bad
    print(("ok   " if ok else "FAIL ") + name + (f": {detail}" if detail else ""))
    bad += 0 if ok else 1


rc, out = sh("uname -r && cat /proc/cmdline && cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor", True)
lines = out.splitlines()
check("kernel", lines[0] == KERNEL, lines[0])
want = ["amd_iommu=off", "ttm.pages_limit=31457280", "amdgpu.gttsize=131072", "amdgpu.cwsr_enable=0"]
check("kernel command line", all(w in lines[1].split() for w in want), "" if all(w in lines[1].split() for w in want) else lines[1])
check("cpu governor", lines[2] == "performance", lines[2])

for be in ("vulkan", "rocm"):
    rc, out = sh(f'B=$HOME/.local/opt/llama.cpp/b10970-{be}; LD_LIBRARY_PATH=$B $B/llama-server --list-devices 2>&1 | tail -3', True)
    check(f"{be} build sees the GPU", "Radeon 8060S" in out, out.splitlines()[-1] if out else "no output")
rc, out = sh("ls $HOME/models/lifeops | wc -l && df -BG --output=avail $HOME | tail -1 && cat /sys/class/hwmon/hwmon5/power1_input && cat /proc/loadavg", True)
n, avail, ppt, load = out.splitlines()[:4]
check("model files present", int(n) >= 4, n)
check("disk free over 10 GB", int(avail.strip().rstrip("G")) > 10, avail.strip())
check("package power sensor reads", int(ppt) > 0, f"{int(ppt)/1e6:.1f} W")
check("machine quiet (5 min load average under 0.5)", float(load.split()[1]) < 0.5, load)
rc, out = sh("ps -eo pcpu,args --sort=-pcpu | sed -n 2,4p | cut -c1-90", True)
top = float(out.splitlines()[0].split()[0]) if out else 0.0
check("no process above 10% CPU right now", top < 10.0, out.splitlines()[0] if out else "")
t0 = time.time(); rc, rt = sh("date +%s.%N", True); t1 = time.time()
off = float(rt.splitlines()[-1]) - (t0 + t1) / 2
check("clock offset to warden under 0.2 s", abs(off) < 0.2, f"{off:+.3f} s")

pw = os.environ.get("TASMOTA_PASSWORD_WARDEN")
try:
    url = f"http://192.168.88.49/cm?user=admin&password={pw}&cmnd=Status%208"
    d = json.load(urllib.request.urlopen(url, timeout=5))
    w = d["StatusSNS"]["ENERGY"]["Power"]
    check("plug reads", 0 < w < 400, f"{w} W")
except Exception as e:
    check("plug reads", False, type(e).__name__)

rc, st = sh(f"cd {REPO} && git status --porcelain -- harness tests PLAN*.md DEVIATIONS.md | wc -l")
check("harness, tests and plans committed", st.strip() == "0", st)
rc, out = sh(f"cd {REPO} && git fetch -q origin && git rev-parse HEAD origin/main && git log -1 --format=%cI origin/main -- {PLAN}")
head, remote, when = (out.splitlines() + ["", "", ""])[:3]
check("plan is on origin/main and HEAD is pushed", head == remote and bool(when), f"plan commit {when}")
rc, out = sh(f"cd {REPO} && python3 -m pytest -q tests 2>&1 | tail -1")
check("tests pass", "passed" in out and "failed" not in out, out)
rc, out = sh("systemctl is-active ollama", True)
check("ollama service state known", out in ("active", "inactive"), out)
print("PREFLIGHT " + ("FAILED" if bad else "PASSED"))
sys.exit(1 if bad else 0)
