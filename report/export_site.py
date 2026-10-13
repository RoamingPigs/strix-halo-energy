#!/usr/bin/env python3
"""Writes what a site needs from this study: class-only SVG figures (no <style>, no style attributes, so they pass a strict
Content-Security-Policy), their stylesheet, copies of the summaries and the evaluation, and PROVENANCE.json with SHA-256 digests.

usage: export_site.py OUT_DIR RUN_DIR      (RUN_DIR holds summary-vulkan.json, summary-rocm.json, evaluation.json, events and raw logs)
"""
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import derive as D  # noqa: E402
import figures as F  # noqa: E402

out, run = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
(out / "figures").mkdir(parents=True, exist_ok=True)
F.CLASS_ONLY = True
V = json.load(open(run / "summary-vulkan.json"))
R = json.load(open(run / "summary-rocm.json"))
EV = json.load(open(run / "evaluation.json"))
SHORT = {"P1": "Vulkan on kernel 38 within 3% of study 1 in every cell", "P2": "ROCm within 25% of Vulkan; slower for the 26B mixture at 64",
         "P3": "ROCm gap shrinks or reverses with context for some model", "P4": "Idle under 25 W and within 2 W of study 1, both backends",
         "P5": "Wall power within 15% between backends, same cell", "P6": "Models rank the same by energy per token in both backends",
         "P7": "Repeat spread under 5% in every cell", "P8": "All 96 cells, 3 repeats; parse error only with the 26B mixture"}
DETAIL = {"P1": f"largest difference {EV['P1']['max_abs_pct']}%", "P2": f"ROCm at {EV['P2']['min_ratio']*100:.0f} to {EV['P2']['max_ratio']*100:.0f}% of Vulkan",
          "P4": f"idle {EV['P4']['vulkan_median_w'][0]:g} W Vulkan, {EV['P4']['rocm_median_w'][0]:g} W ROCm, {EV['P4']['study1_median_w'][0]:g} W in study 1",
          "P5": f"ROCm wall power {EV['P5']['min']*100:.0f} to {EV['P5']['max']*100:.0f}% of Vulkan", "P7": f"largest spread {EV['P7']['max_pct']}%",
          "P8": f"{EV['P8']['parse_error_requests']} requests recovered after the parse error, {EV['P8']['failed']} failed cells, {EV['P8']['contaminated']} contaminated"}
figs = {"speed-vs-depth": F.speed_vs_depth(V, R, "Vulkan", "ROCm"), "energy-per-token": F.energy_ladder(V, R, "Vulkan", "ROCm"),
        "where-watts-go": F.where_watts_go(V, "Vulkan"), "power-timeline": F.power_timeline(run, "gemma4-26b-a4b-q4", 4096, 1, "vulkan"),
        "ratio": F.ratio_heatmap(V, R, "Vulkan", "ROCm"),
        "scorecard": F.scorecard(V, "", items=[(f"{k} {SHORT[k]}", v["holds"]) for k, v in EV.items()], detail=DETAIL)}
for k, v in figs.items():
    assert "<style" not in v and "style=" not in v, k
    (out / "figures" / f"{k}.svg").write_text(v)
css = re.search(r"<style>(.*?)</style>", F.STYLE, re.S).group(1).strip()
(out / "figures.css").write_text(css + "\n")
(out / "findings.json").write_text(json.dumps([{"label": a, "text": b} for a, b in D.findings(V, R, EV)], indent=1) + "\n")
(out / "table-vulkan.json").write_text(json.dumps(D.table(V), indent=1) + "\n")
(out / "table-rocm.json").write_text(json.dumps(D.table(R), indent=1) + "\n")
# Nominal parameter counts, read from the model names (9B, 12B, 26B-A4B, 35B-A3B); bytes are the GGUF file sizes in meta.json.
NOMINAL = {"qwen35-9b-q4km": (9.0, 9.0), "gemma4-12b-q4": (12.0, 12.0), "gemma4-26b-a4b-q4": (26.0, 4.0), "qwen36-35b-a3b-q8": (35.0, 3.0)}
meta = json.load(open(run / "meta.json"))
(out / "models.json").write_text(json.dumps([
    {"id": k, "label": lab, "short": sh, "kind": "dense" if NOMINAL[k][0] == NOMINAL[k][1] else "moe", "total_b": NOMINAL[k][0], "active_b": NOMINAL[k][1],
     "file_bytes": meta["models"][k]["bytes"]} for k, lab, sh in F.MODELS], indent=1) + "\n")
for name in ("summary-vulkan.json", "summary-rocm.json", "evaluation.json"):
    shutil.copy(run / name, out / name)
repo = pathlib.Path(__file__).parent.parent
commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "PROVENANCE.json")
prov = {"source": "https://github.com/RoamingPigs/strix-halo-energy", "source_commit": commit, "run": run.name,
        "files": {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
(out / "PROVENANCE.json").write_text(json.dumps(prov, indent=1) + "\n")
print("exported", len(files), "files to", out)
