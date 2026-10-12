#!/usr/bin/env python3
"""compare.py A.json B.json "label A" "label B" OUT.md : cell by cell, B over A, with repeat ranges.
A difference is called real only when the min to max ranges of the repeats do not overlap (PLAN.md, S6)."""
import json
import sys

METRICS = [("tok_per_s", "tok/s", 1), ("wall_mean_w", "wall W", 1), ("ppt_mean_w", "package W", 1), ("wall_net_j_per_tok", "wall net J/tok", 2)]


def verdict(a, b):
    if b["min"] > a["max"]:
        return "higher"
    if b["max"] < a["min"]:
        return "lower"
    return "overlap"


def compare(pa, pb, la, lb):
    A, B = json.load(open(pa))["cells"], json.load(open(pb))["cells"]
    L = [f"# {lb} against {la}", "", f"Ratio is {lb} over {la} (mean over repeats). 'overlap' means the repeat ranges overlap, so no claim.", "",
         "| Cell | " + " | ".join(m[1] for m in METRICS) + " |", "|---|" + "---|" * len(METRICS)]
    for k in sorted(set(A) & set(B)):
        cols = []
        for key, _, dp in METRICS:
            a, b = A[k][key], B[k][key]
            cols.append(f"{b['mean'] / a['mean']:.3f} ({verdict(a, b)}; n {a['n']}/{b['n']})")
        L.append(f"| {k} | " + " | ".join(cols) + " |")
    only = sorted(set(A) ^ set(B))
    if only:
        L += ["", "In only one of the two: " + ", ".join(only)]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    pa, pb, la, lb, out = sys.argv[1:6]
    open(out, "w").write(compare(pa, pb, la, lb))
