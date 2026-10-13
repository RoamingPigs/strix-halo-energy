#!/usr/bin/env python3
"""Checks the expectations P1 to P8 of PLAN-3.md against the paired run. usage: evaluate_plan3.py RUN_DIR STUDY1_SUMMARY.json OUT.json"""
import json
import sys

import numpy as np

run, s1p, outp = sys.argv[1:4]
V = json.load(open(f"{run}/summary-vulkan.json"))
R = json.load(open(f"{run}/summary-rocm.json"))
S1 = json.load(open(s1p))
cells = sorted(set(V["cells"]) & set(R["cells"]))
mean = lambda S, k, m: S["cells"][k][m]["mean"]
res = {}

d = {k: 100 * (mean(V, k, "tok_per_s") / mean(S1, k, "tok_per_s") - 1) for k in cells if k in S1["cells"]}
res["P1"] = {"claim": "Vulkan now within 3% of study 1 tokens per second in every cell", "holds": max(abs(x) for x in d.values()) <= 3,
             "max_abs_pct": round(max(abs(x) for x in d.values()), 2), "mean_pct": round(float(np.mean(list(d.values()))), 2),
             "worst": sorted(d.items(), key=lambda kv: -abs(kv[1]))[:3]}

ratio = {k: mean(R, k, "tok_per_s") / mean(V, k, "tok_per_s") for k in cells}
k64 = "gemma4-26b-a4b-q4@64"
res["P2"] = {"claim": "ROCm within 25% of Vulkan in every cell, and below Vulkan for the 26B mixture at depth 64",
             "holds": all(0.75 <= r <= 1.25 for r in ratio.values()) and ratio[k64] < 1,
             "min_ratio": round(min(ratio.values()), 3), "max_ratio": round(max(ratio.values()), 3), "ratio_26b_64": round(ratio[k64], 3)}

models = sorted({k.split("@")[0] for k in cells})
gap = {m: (ratio[f"{m}@32768"] - ratio[f"{m}@64"]) for m in models}
res["P3"] = {"claim": "for at least one model the ROCm minus Vulkan gap shrinks or reverses from 64 to 32k",
             "holds": any((abs(ratio[f"{m}@32768"] - 1) < abs(ratio[f"{m}@64"] - 1)) or ((ratio[f"{m}@32768"] - 1) * (ratio[f"{m}@64"] - 1) < 0) for m in models),
             "ratio_64_to_32k": {m: [round(ratio[f"{m}@64"], 3), round(ratio[f"{m}@32768"], 3)] for m in models}}

def idle_med(S):
    v = [x["wall_w_median"] for k, x in S["idle"].items() if k.startswith("bare_idle")]
    return round(float(np.median(v)), 2), round(min(v), 1), round(max(v), 1)
i1 = idle_med(S1)
iv, ir = idle_med(V), idle_med(R)
res["P4"] = {"claim": "idle wall power under 25 W and within 2 W of study 1, both backends",
             "holds": all(x[0] < 25 and abs(x[0] - i1[0]) <= 2 for x in (iv, ir)),
             "study1_median_w": i1, "vulkan_median_w": iv, "rocm_median_w": ir}

wr = {k: mean(R, k, "wall_mean_w") / mean(V, k, "wall_mean_w") for k in cells}
res["P5"] = {"claim": "wall power under load within 15% between backends, same cell", "holds": all(0.85 <= r <= 1.15 for r in wr.values()),
             "min": round(min(wr.values()), 3), "max": round(max(wr.values()), 3)}

def rank(S, depth):
    return [m for m, _ in sorted(((m, mean(S, f"{m}@{depth}", "wall_net_j_per_tok")) for m in models), key=lambda x: x[1])]
rk = {dp: (rank(V, dp), rank(R, dp)) for dp in (64, 4096, 16384, 32768)}
res["P6"] = {"claim": "models rank the same by wall net J/token in both backends (checked at each depth)", "holds": all(a == b for a, b in rk.values()),
             "ranking_vulkan_vs_rocm": {str(dp): {"vulkan": a, "rocm": b, "same": a == b} for dp, (a, b) in rk.items()}}

spread = {}
for nm, S in (("vulkan", V), ("rocm", R)):
    for k in cells:
        c = S["cells"][k]["tok_per_s"]
        spread[f"{nm}:{k}"] = 100 * (c["max"] - c["min"]) / c["mean"]
res["P7"] = {"claim": "repeat spread in tokens per second under 5% in every cell of both backends", "holds": max(spread.values()) < 5,
             "max_pct": round(max(spread.values()), 2), "worst": sorted(((k, round(v, 2)) for k, v in spread.items()), key=lambda kv: -kv[1])[:3]}

ev = [json.loads(l) for l in open(f"{run}/events.jsonl")]
ends = [e for e in ev if e["kind"] == "cell_end"]
n_by = {}
for e in ends:
    n_by.setdefault((e["backend"], e["model"], e["depth"]), 0)
    n_by[(e["backend"], e["model"], e["depth"])] += 1
pe_models = sorted({e["model"] for e in ev if e["kind"] == "decode_request" and e["timings"].get("parse_error")})
res["P8"] = {"claim": "all 96 cells complete with 3 repeats; parse errors only with the 26B mixture", "holds": len(ends) == 96 and all(v == 3 for v in n_by.values())
             and len(n_by) == 32 and pe_models in ([], ["gemma4-26b-a4b-q4"]),
             "cells_ended": len(ends), "combos": len(n_by), "repeat_counts": sorted(set(n_by.values())),
             "failed": sum(1 for e in ev if e["kind"] == "cell_failed"), "contaminated": sum(1 for e in ends if e["contaminated"]),
             "parse_error_requests": sum(1 for e in ev if e["kind"] == "decode_request" and e["timings"].get("parse_error")), "parse_error_models": pe_models}
json.dump(res, open(outp, "w"), indent=1)
for k, v in res.items():
    print(k, "HELD" if v["holds"] else "WRONG", "|", {a: b for a, b in v.items() if a not in ("claim", "holds")} if False else "")
