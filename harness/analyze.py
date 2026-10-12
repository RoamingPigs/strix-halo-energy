#!/usr/bin/env python3
"""Every pre-specified analysis in PLAN.md, nothing else.

usage: analyze.py RESULTS_DIR   (needs events.jsonl, hwmon.csv, plug.csv, meta.json)
writes cells.csv, summary.json and REPORT.md into RESULTS_DIR.
"""
import csv
import json
import pathlib
import statistics as st
import sys

import numpy as np

LAGS = np.arange(0.0, 10.01, 0.25)


def load_csv(path, cols):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                rows.append([float(r[c]) for c in cols])
            except (ValueError, KeyError):
                continue
    return np.array(rows, dtype=float)


def load_events(path):
    return [json.loads(line) for line in open(path) if line.strip()]


class Series:
    """A piecewise-linear signal; `t` in unix seconds."""

    def __init__(self, t, v):
        o = np.argsort(t)
        self.t, self.v = np.asarray(t)[o], np.asarray(v)[o]

    def at(self, tt):
        return np.interp(tt, self.t, self.v)

    def mean(self, t0, t1, step=0.1):
        g = np.arange(t0, t1 + 1e-9, step)
        return float(np.mean(self.at(g)))

    def energy(self, t0, t1, step=0.1):
        g = np.arange(t0, t1 + 1e-9, step)
        y = self.at(g)
        return float(np.trapezoid(y, g))

    def median(self, t0, t1):
        m = (self.t >= t0) & (self.t <= t1)
        return float(np.median(self.v[m])) if m.any() else float("nan")


def estimate_lag(plug: Series, ppt: Series, t0, t1):
    """Plug reading at time tau reflects power at tau - L. Find L that best matches plug(tau) ~ a*ppt(tau - L) + b."""
    g = np.arange(t0, t1, 1.0)
    y = plug.at(g)
    best = (None, float("inf"), None)
    for L in LAGS:
        x = ppt.at(g - L)
        A = np.vstack([x, np.ones_like(x)]).T
        coef, res, *_ = np.linalg.lstsq(A, y, rcond=None)
        sse = float(np.sum((A @ coef - y) ** 2))
        if sse < best[1]:
            best = (float(L), sse, coef.tolist())
    return best[0], best[2]


def shifted(plug: Series, lag: float) -> Series:
    """True-power estimate: the value read at tau describes time tau - lag."""
    return Series(plug.t - lag, plug.v)


def cell_rows(events, wall: Series, ppt: Series, hw, lag):
    by_cell = {}
    for e in events:
        if "model" in e and "depth" in e and "round" in e:
            by_cell.setdefault((e["model"], e["depth"], e["round"], e.get("rerun", 0)), []).append(e)
    rows = []
    for (m, d, rnd, _), evs in by_cell.items():
        # A rerun of a contaminated cell repeats the same (model, depth, round): keep only the last attempt.
        starts = [i for i, e in enumerate(evs) if e["kind"] == "cell_start"]
        evs = evs[starts[-1]:] if starts else evs
        win = next((e for e in evs if e["kind"] == "window"), None)
        end = next((e for e in evs if e["kind"] == "cell_end"), None)
        if not win or not end:
            continue
        before = next(e for e in evs if e["kind"] == "idle" and e["label"] == "settle_before")
        after = next(e for e in evs if e["kind"] == "idle" and e["label"] == "settle_after")
        reqs = [e for e in evs if e["kind"] == "decode_request"]
        t0, t1 = win["t0"], win["t1"]
        dur = t1 - t0
        tokens = win["tokens"]
        dec_ms = sum((r["timings"].get("predicted_ms") or 0) for r in reqs)
        row = {"model": m, "depth": d, "round": rnd, "window_s": round(dur, 2), "tokens": tokens,
               "requests": len(reqs), "cache_reused": win["cache_reused"], "contaminated": end["contaminated"],
               "tok_per_s": tokens / (dec_ms / 1000.0) if dec_ms else float("nan"),
               "window_tok_per_s": tokens / dur if dur else float("nan"),
               "ollama_requests": end.get("ollama_requests", 0),
               "parse_error_requests": sum(1 for r in reqs if r["timings"].get("parse_error"))}
        # baselines: last 20 s of settle_before, and 10 s to 30 s of settle_after
        b0 = (before["t1"] - 20, before["t1"])
        b1 = (after["t0"] + 10, after["t0"] + 30)

        def base(sig):
            return 0.5 * (sig.mean(*b0) + sig.mean(*b1))

        for name, sig in (("wall", wall), ("ppt", ppt)):
            gross_j = sig.energy(t0, t1)
            bl = base(sig)
            row[f"{name}_mean_w"] = gross_j / dur
            row[f"{name}_idle_w"] = bl
            row[f"{name}_gross_j_per_tok"] = gross_j / tokens
            row[f"{name}_net_j_per_tok"] = (gross_j - bl * dur) / tokens
        row["wall_ppt_ratio"] = row["wall_mean_w"] / row["ppt_mean_w"]
        hmask = (hw[:, 0] >= t0) & (hw[:, 0] <= t1)
        row["gpu_temp_max_c"] = float(np.nanmax(hw[hmask, 2])) if hmask.any() else float("nan")
        row["cpu_temp_max_c"] = float(np.nanmax(hw[hmask, 3])) if hmask.any() else float("nan")
        row["gpu_clock_mean_mhz"] = float(np.nanmean(hw[hmask, 4])) if hmask.any() else float("nan")
        row["throttled"] = row["gpu_temp_max_c"] >= 95
        row["short_window"] = dur < 100
        rows.append(row)
    return rows


def sensitivity(events, plug: Series, ppt, hw, lag):
    """Net wall J/token per cell with the lag at 0, lag-2, lag, lag+2."""
    out = {}
    for L in sorted({0.0, max(0.0, lag - 2), lag, lag + 2}):
        rows = cell_rows(events, shifted(plug, L), ppt, hw, L)
        for r in rows:
            out.setdefault((r["model"], r["depth"], r["round"]), {})[L] = r["wall_net_j_per_tok"]
    return out


def summarize(rows):
    cells = {}
    for r in rows:
        if r["contaminated"] or r["short_window"]:
            continue
        cells.setdefault((r["model"], r["depth"]), []).append(r)
    agg = {}
    for k, rs in cells.items():
        def stat(f):
            v = [x[f] for x in rs]
            return {"mean": st.fmean(v), "min": min(v), "max": max(v), "n": len(v)}
        agg[k] = {f: stat(f) for f in ("tok_per_s", "wall_mean_w", "ppt_mean_w", "wall_ppt_ratio", "wall_gross_j_per_tok",
                                       "wall_net_j_per_tok", "ppt_gross_j_per_tok", "ppt_net_j_per_tok")}
        agg[k]["throttled"] = any(x["throttled"] for x in rs)
        agg[k]["cache_reused"] = all(x["cache_reused"] for x in rs)
    return agg


def idle_stats(events, wall: Series, ppt: Series):
    out = {}
    for label in ("bare_idle_start", "bare_idle_end", "bare_idle_block", "loaded_idle"):
        segs = [e for e in events if e["kind"] == "idle" and e["label"] == label]
        w, p = [], []
        for s in segs:
            t0, t1 = s["t0"] + 15, s["t1"]
            w.append(wall.median(t0, t1))
            p.append(ppt.median(t0, t1))
        if w:
            out[label] = {"n": len(w), "wall_w_median": st.median(w), "wall_w_range": [min(w), max(w)],
                          "ppt_w_median": st.median(p), "ppt_w_range": [min(p), max(p)]}
    return out


def overlap(a, b):
    return not (a["max"] < b["min"] or b["max"] < a["min"])


def expectations(agg, idle, rows, models):
    res = {}
    bare = [idle[k]["wall_w_median"] for k in ("bare_idle_start", "bare_idle_end") if k in idle]
    res["E1 bare idle wall power under 25 W"] = {"holds": bool(bare) and max(bare) < 25, "values_w": bare}
    jt = {k: v["wall_net_j_per_tok"] for k, v in agg.items()}
    allj = [x["mean"] for x in jt.values()]
    moe = [x["mean"] for (m, d), x in jt.items() if models[m]["kind"] == "moe"]
    dense = [x["mean"] for (m, d), x in jt.items() if models[m]["kind"] == "dense"]
    res["E2 wall net J/token between 1 and 5 for all cells, MoE below dense"] = {
        "in_range": bool(allj) and all(1 <= x <= 5 for x in allj), "range": [min(allj), max(allj)] if allj else None,
        "moe_mean": st.fmean(moe) if moe else None, "dense_mean": st.fmean(dense) if dense else None,
        "moe_lower": bool(moe and dense and st.fmean(moe) < st.fmean(dense))}
    ratios = [v["wall_ppt_ratio"]["mean"] for v in agg.values()]
    pidle = [idle[k]["wall_w_median"] / idle[k]["ppt_w_median"] for k in ("bare_idle_start", "bare_idle_end") if k in idle]
    res["E3 wall/package ratio above 2 at idle and 1.2 to 1.6 under load"] = {
        "idle_ratio": pidle, "load_ratio_range": [min(ratios), max(ratios)] if ratios else None,
        "holds": bool(pidle and ratios and min(pidle) > 2 and 1.2 <= min(ratios) and max(ratios) <= 1.6)}
    e4 = {}
    for m in models:
        a = agg.get((m, 64)); z = agg.get((m, 32768))
        if a and z:
            e4[m] = {"tok_s_change_pct": 100 * (z["tok_per_s"]["mean"] / a["tok_per_s"]["mean"] - 1),
                     "j_per_tok_change_pct": 100 * (z["wall_net_j_per_tok"]["mean"] / a["wall_net_j_per_tok"]["mean"] - 1),
                     "ranges_overlap_tok_s": overlap(a["tok_per_s"], z["tok_per_s"])}
    res["E4 tok/s falls 10 to 50% from depth 64 to 32768, J/token rises"] = {
        "per_model": e4, "holds": bool(e4) and all(-50 <= v["tok_s_change_pct"] <= -10 and v["j_per_tok_change_pct"] > 0 for v in e4.values())}
    q8, q4 = agg.get(("qwen36-35b-a3b-q8", 64)), agg.get(("gemma4-26b-a4b-q4", 64))
    res["E5 Q8 35B MoE slower than Q4 26B MoE at depth 64"] = {
        "holds": bool(q8 and q4 and q8["tok_per_s"]["mean"] < q4["tok_per_s"]["mean"]),
        "q8_tok_s": q8["tok_per_s"] if q8 else None, "q4_tok_s": q4["tok_per_s"] if q4 else None}
    spreads = {f"{m}@{d}": 100 * (v["tok_per_s"]["max"] - v["tok_per_s"]["min"]) / v["tok_per_s"]["mean"] for (m, d), v in agg.items()}
    res["E6 repeat spread in tok/s under 5% in every cell"] = {"holds": bool(spreads) and max(spreads.values()) < 5,
                                                              "max_spread_pct": max(spreads.values()) if spreads else None}
    return res


def crosscheck(plug_rows, t0, t1):
    """S7: plug cumulative kWh against the integral of its polled watts, over [t0, t1].
    Sampling gaps longer than 60 s (a stopped and resumed run) split the span; each piece is compared and summed."""
    m = (plug_rows[:, 0] >= t0) & (plug_rows[:, 0] <= t1)
    rows = plug_rows[m]
    t = (rows[:, 0] + rows[:, 1]) / 2
    cuts = [0] + [i + 1 for i in range(len(t) - 1) if t[i + 1] - t[i] > 60] + [len(t)]
    integral_wh = counter_wh = 0.0
    for a, b in zip(cuts, cuts[1:]):
        if b - a < 2:
            continue
        integral_wh += float(np.trapezoid(rows[a:b, 2], t[a:b]) / 3600.0)
        counter_wh += float((rows[b - 1, 7] - rows[a, 7]) * 1000.0)
    return {"integral_wh": integral_wh, "counter_wh": counter_wh, "segments": len(cuts) - 1,
            "diff_pct": 100 * (integral_wh - counter_wh) / counter_wh if counter_wh else None}


def run(d: pathlib.Path, models_path: pathlib.Path):
    models = json.loads(models_path.read_text())
    events = load_events(d / "events.jsonl")
    hw = load_csv(d / "hwmon.csv", ["t_unix", "ppt_w", "gpu_temp_c", "cpu_temp_c", "gpu_clock_mhz", "gpu_busy_pct"])
    plug_rows = load_csv(d / "plug.csv", ["t_send", "t_recv", "power_w", "apparent_va", "voltage_v", "current_a", "factor", "total_kwh"])
    plug = Series((plug_rows[:, 0] + plug_rows[:, 1]) / 2, plug_rows[:, 2])
    ppt = Series(hw[:, 0], hw[:, 1])
    step = [e for e in events if e["kind"] in ("idle", "step_load") and (e.get("label", "").startswith("step") or e["kind"] == "step_load")]
    lag, coef = (0.0, None)
    if step:
        lag, coef = estimate_lag(plug, ppt, min(e["t0"] for e in step) - 5, max(e["t1"] for e in step) + 5)
    wall = shifted(plug, lag)
    rows = cell_rows(events, wall, ppt, hw, lag)
    sens = sensitivity(events, plug, ppt, hw, lag) if rows else {}
    for r in rows:
        r["wall_net_j_per_tok_by_lag"] = {str(k): v for k, v in sens.get((r["model"], r["depth"], r["round"]), {}).items()}
    agg = summarize(rows)
    idle = idle_stats(events, wall, ppt)
    exp = expectations(agg, idle, rows, models) if agg else {}
    t_first = min(e["t"] for e in events); t_last = max(e["t"] for e in events)
    cc = crosscheck(plug_rows, t_first, t_last)
    out = {"lag_s": lag, "lag_fit": coef, "idle": idle, "crosscheck_total_counter": cc, "expectations": exp,
           "cells": {f"{m}@{d}": v for (m, d), v in agg.items()}, "n_cells": len(rows),
           "n_contaminated": sum(1 for r in rows if r["contaminated"]), "n_short": sum(1 for r in rows if r["short_window"]),
           "n_throttled": sum(1 for r in rows if r["throttled"]),
           "n_cells_with_parse_error": sum(1 for r in rows if r["parse_error_requests"]),
           "n_parse_error_requests": sum(r["parse_error_requests"] for r in rows)}
    (d / "summary.json").write_text(json.dumps(out, indent=1))
    if rows:
        keys = [k for k in rows[0] if k != "wall_net_j_per_tok_by_lag"]
        with open(d / "cells.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    write_report(d, out, agg, models)
    return out


def write_report(d, out, agg, models):
    L = ["# Results (auto-generated by analyze.py)", "",
         f"Plug response lag estimated from the load step: {out['lag_s']:.2f} s. Cells: {out['n_cells']}; "
         f"contaminated {out['n_contaminated']}, short window {out['n_short']}, throttled {out['n_throttled']}.",
         f"Requests the server answered with a response-parse error (timings taken from its log, see DEVIATIONS.md): "
         f"{out['n_parse_error_requests']} in {out['n_cells_with_parse_error']} cells.", "",
         "## S1. Idle", "", "| Segment | Wall W (median, range of medians) | Package W |", "|---|---|---|"]
    for k, v in out["idle"].items():
        L.append(f"| {k} (n={v['n']}) | {v['wall_w_median']:.1f} ({v['wall_w_range'][0]:.1f} to {v['wall_w_range'][1]:.1f}) | "
                 f"{v['ppt_w_median']:.1f} ({v['ppt_w_range'][0]:.1f} to {v['ppt_w_range'][1]:.1f}) |")
    L += ["", "## S2 to S5. Per model and depth (mean, with min to max over repeats)", "",
          "| Model | Depth | tok/s | Wall W | Package W | Wall/pkg | Wall net J/tok | Wall gross J/tok | Pkg net J/tok | n |", "|---|---:|---|---|---|---|---|---|---|---:|"]
    f = lambda s, p=2: f"{s['mean']:.{p}f} ({s['min']:.{p}f} to {s['max']:.{p}f})"
    for (m, dpt) in sorted(agg, key=lambda k: (k[0], k[1])):
        a = agg[(m, dpt)]
        L.append(f"| {models[m]['label']} | {dpt} | {f(a['tok_per_s'], 1)} | {f(a['wall_mean_w'], 1)} | {f(a['ppt_mean_w'], 1)} | "
                 f"{f(a['wall_ppt_ratio'])} | {f(a['wall_net_j_per_tok'])} | {f(a['wall_gross_j_per_tok'])} | {f(a['ppt_net_j_per_tok'])} | {a['tok_per_s']['n']} |")
    L += ["", "## S7. Plug energy counter against integrated watts", "",
          f"Integrated {out['crosscheck_total_counter']['integral_wh']:.1f} Wh, counter {out['crosscheck_total_counter']['counter_wh']:.1f} Wh "
          f"(difference {out['crosscheck_total_counter']['diff_pct']:.1f}%). Both come from the same plug, so this checks sampling, not accuracy.",
          "", "## Expectations written in advance", ""]
    for k, v in out["expectations"].items():
        L.append(f"- **{k}**: `{json.dumps(v)[:400]}`")
    (d / "REPORT.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    base = pathlib.Path(__file__).parent
    run(pathlib.Path(sys.argv[1]), base / "models.json")
