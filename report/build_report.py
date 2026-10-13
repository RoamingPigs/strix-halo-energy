#!/usr/bin/env python3
"""Builds the standalone report page (inline SVG, no scripts) from the analysis output. Every number comes from the data.

usage: build_report.py OUT.html RAW_DIR SUMMARY_VULKAN.json [SUMMARY_ROCM.json] [--title=...] [--status=...]
"""
import json
import pathlib
import subprocess
import sys
from html import escape as e

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import figures as F  # noqa: E402

CSS = """
:root{--paper:#f6f3ec;--surface:#fffdf8;--ink:#15130f;--ink2:#3a362d;--mut:#6b6558;--rule:#d9d3c3;--rule2:#b9b19b;--a:#1a47c9;--b:#c2410c;--ok:#0b6b4d;
--f-bg:#fffdf8}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:17px/1.6 "Source Serif 4",Georgia,serif}
.wrap{max-width:46rem;margin:0 auto;padding:2.5rem 1.25rem 4rem}
h1,h2,h3,.sans{font-family:Inter,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
h1{font-size:clamp(1.9rem,1.2rem+3vw,2.9rem);line-height:1.08;letter-spacing:-.03em;margin:.4rem 0 .6rem}
h2{font-size:1.35rem;letter-spacing:-.015em;margin:2.6rem 0 .6rem;padding-top:1rem;border-top:1px solid var(--rule)}
.kicker{font:600 .78rem/1 Inter,system-ui,sans-serif;letter-spacing:.09em;text-transform:uppercase;color:var(--mut)}
.lede{font-size:1.2rem;color:var(--ink2);margin:.2rem 0 1rem}
.status{display:inline-block;font:600 .8rem/1 Inter,system-ui,sans-serif;background:#f8ecd2;color:#8a5200;border-radius:3px;padding:.35rem .5rem;margin:.3rem 0 1rem}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(9rem,1fr));gap:.7rem;margin:1.4rem 0}
.stat{background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:.8rem .9rem}
.stat b{display:block;font:650 1.9rem/1.1 Inter,system-ui,sans-serif;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.stat span{font:400 .82rem/1.35 Inter,system-ui,sans-serif;color:var(--mut)}
figure{margin:1.4rem 0;padding:1rem;background:var(--surface);border:1px solid var(--rule);border-radius:6px}
figcaption{font:400 .85rem/1.5 Inter,system-ui,sans-serif;color:var(--mut);margin-top:.6rem}figcaption strong{color:var(--ink2)}
table{border-collapse:collapse;width:100%;font:400 .85rem/1.4 Inter,system-ui,sans-serif;font-variant-numeric:tabular-nums}
th,td{border-bottom:1px solid var(--rule);padding:.4rem .5rem;text-align:right}th:first-child,td:first-child{text-align:left}th{font-weight:600;color:var(--ink2)}
.tw{overflow-x:auto}a{color:#1a47c9}code{font:.85em ui-monospace,Menlo,Consolas,monospace}
.limits li{margin:.35rem 0}
@media print{body{background:#fff}.wrap{max-width:none;padding:0}figure,.stat{break-inside:avoid}h2{break-after:avoid}}
"""


def git(*a):
    try:
        return subprocess.run(["git", "-C", str(pathlib.Path(__file__).parent.parent), *a], capture_output=True, text=True).stdout.strip()
    except Exception:
        return ""


def cells(S):
    return [(mk, d, S["cells"][f"{mk}@{d}"]) for mk, _, _ in F.MODELS for d in F.DEPTHS if f"{mk}@{d}" in S["cells"]]


def table(S, label):
    rows = ["<tr><th>Model</th><th>Context</th><th>tok/s</th><th>Wall W</th><th>Package W</th><th>Wall net J/token</th><th>Package net J/token</th><th>Repeats</th></tr>"]
    lab = {k: l for k, l, _ in F.MODELS}
    for mk, d, c in cells(S):
        r = lambda key, p: f"{c[key]['mean']:.{p}f}"
        rows.append(f"<tr><td>{e(lab[mk])}</td><td>{F.DEPTH_LABEL[d]}</td><td>{r('tok_per_s',1)}</td><td>{r('wall_mean_w',0)}</td><td>{r('ppt_mean_w',0)}</td>"
                    f"<td>{r('wall_net_j_per_tok',2)}</td><td>{r('ppt_net_j_per_tok',2)}</td><td>{c['tok_per_s']['n']}</td></tr>")
    return f'<div class="tw"><table aria-label="{e(label)}">{"".join(rows)}</table></div>'


def findings(SA, SB, EV, la, lb):
    """Plain sentences computed from the two summaries. Direction only where the repeat ranges do not overlap."""
    lab = {k: l for k, l, _ in F.MODELS}
    shorts = {k: sh for k, _, sh in F.MODELS}
    out = []
    keys = [f"{mk}@{d}" for mk, _, _ in F.MODELS for d in F.DEPTHS if f"{mk}@{d}" in SA["cells"] and f"{mk}@{d}" in SB["cells"]]
    def side(k, m):
        a, b = SA["cells"][k][m], SB["cells"][k][m]
        return "higher" if b["min"] > a["max"] else "lower" if b["max"] < a["min"] else "overlap"
    sp = [SB["cells"][k]["tok_per_s"]["mean"] / SA["cells"][k]["tok_per_s"]["mean"] for k in keys]
    lower = sum(1 for k in keys if side(k, "tok_per_s") == "lower")
    out.append(f"<strong>Speed.</strong> {lb} decoded more slowly than {la} in {lower} of {len(keys)} cells, by {100-max(sp)*100:.0f} to {100-min(sp)*100:.0f}%, and the repeat ranges of the two backends never overlap in those cells. It was never faster.")
    for mk, _, _ in F.MODELS:
        ks = [f"{mk}@{d}" for d in F.DEPTHS if f"{mk}@{d}" in keys]
        r = [SB["cells"][k]["wall_net_j_per_tok"]["mean"] / SA["cells"][k]["wall_net_j_per_tok"]["mean"] for k in ks]
        dirs = {side(k, "wall_net_j_per_tok") for k in ks}
        word = "less" if dirs == {"lower"} else "more" if dirs == {"higher"} else "about the same (the repeat ranges overlap in some cells)"
        out.append(f"<strong>Energy, {shorts[mk]}.</strong> {lb} used {word} energy per token than {la}: {min(r)*100-100:+.0f} to {max(r)*100-100:+.0f}% across the four context lengths (wall plug, net of idle).")
    if EV:
        out.append(f"<strong>Repeatability.</strong> {la} on the newer kernel, on another day, matched study 1 within {EV['P1']['max_abs_pct']}% in every one of the 16 cells. Idle power was {EV['P4']['vulkan_median_w'][0]:g} W against {EV['P4']['study1_median_w'][0]:g} W.")
    return "<ul>" + "".join(f"<li>{x}</li>" for x in out) + "</ul>"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    out, raw, pa = pathlib.Path(args[0]), args[1], args[2]
    pb = args[3] if len(args) > 3 else None
    SA = json.load(open(pa))
    SB = json.load(open(pb)) if pb else None
    la, lb = "Vulkan", "ROCm"
    title = opts.get("title", "Vulkan or ROCm? Speed and energy per token on one mini PC" if SB else "What a local AI model costs in energy, measured on one mini PC")
    status = opts.get("status", "Self-published. Not peer reviewed. One machine.")
    flags = F.held_flags(SA)
    n_ex, held = len(flags), sum(1 for _, ok in flags if ok)
    ca = cells(SA)
    toks = [c["tok_per_s"]["mean"] for _, _, c in ca]
    jw = [c["wall_net_j_per_tok"]["mean"] for _, _, c in ca]
    idle = SA["idle"].get("bare_idle_block") or next(iter(SA["idle"].values()))
    cc = SA["crosscheck_total_counter"]
    stats = [(f"{idle['wall_w_median']:.0f} W", "at the wall when the machine sits idle"),
             (f"{min(jw):.1f} to {max(jw):.1f}", "joules per token, net of idle, across all models and contexts"),
             (f"{max(toks):.0f}", "tokens per second at best"),
             (f"{SA['n_cells']}", f"measured cells on {la}" + (f", {SB['n_cells']} on {lb}" if SB else "")),
             (f"{held} of {n_ex}", "expectations written in advance held"),
             (f"{abs(cc['diff_pct']):.1f}%", "gap between the plug's own energy counter and the sum of its readings")]
    if SB:
        rr = [SB["cells"][k]["tok_per_s"]["mean"] / SA["cells"][k]["tok_per_s"]["mean"] for k in SA["cells"] if k in SB["cells"]]
        stats.insert(2, (f"{min(rr)*100:.0f} to {max(rr)*100:.0f}%", f"{lb} decode speed as a share of {la}"))
    figs = {}
    d = pathlib.Path(opts.get("figdir", out.parent / "figures"))
    d.mkdir(parents=True, exist_ok=True)
    figs["speed"] = F.speed_vs_depth(SA, SB, la, lb)
    figs["energy"] = F.energy_ladder(SA, SB, la, lb)
    figs["watts"] = F.where_watts_go(SA, la)
    figs["timeline"] = F.power_timeline(raw, "gemma4-26b-a4b-q4", 4096, 1, "vulkan" if SB else None)
    ev_path = opts.get("eval")
    EV = json.load(open(ev_path)) if ev_path else None
    if EV:
        short = {"P1": "Vulkan on kernel 38 within 3% of study 1 in every cell", "P2": "ROCm within 25% of Vulkan; slower for the 26B mixture at 64",
                 "P3": "ROCm gap shrinks or reverses with context for some model", "P4": "Idle under 25 W and within 2 W of study 1, both backends",
                 "P5": "Wall power within 15% between backends, same cell", "P6": "Models rank the same by energy per token in both backends",
                 "P7": "Repeat spread under 5% in every cell", "P8": "All 96 cells, 3 repeats; parse error only with the 26B mixture"}
        det = {"P1": f"largest difference {EV['P1']['max_abs_pct']}%", "P2": f"ROCm at {EV['P2']['min_ratio']*100:.0f} to {EV['P2']['max_ratio']*100:.0f}% of Vulkan",
               "P4": f"idle {EV['P4']['vulkan_median_w'][0]:g} W Vulkan, {EV['P4']['rocm_median_w'][0]:g} W ROCm, {EV['P4']['study1_median_w'][0]:g} W in study 1",
               "P5": f"ROCm wall power {EV['P5']['min']*100:.0f} to {EV['P5']['max']*100:.0f}% of Vulkan", "P7": f"largest spread {EV['P7']['max_pct']}%",
               "P8": f"{EV['P8']['parse_error_requests']} requests recovered after the parse error, {EV['P8']['failed']} failed cells, {EV['P8']['contaminated']} contaminated"}
        figs["score"] = F.scorecard(SA, "", items=[(f"{k} {short[k]}", v["holds"]) for k, v in EV.items()], detail=det)
        flags = [(k, v["holds"]) for k, v in EV.items()]
        n_ex, held = len(flags), sum(1 for _, ok in flags if ok)
        stats[-2] = (f"{held} of {n_ex}", "expectations written in advance held")
    else:
        figs["score"] = F.scorecard(SA, "")
    if SB:
        figs["ratio"] = F.ratio_heatmap(SA, SB, la, lb)
    for k, v in figs.items():
        (d / f"{k}.svg").write_text(v)
    ex = SA["expectations"]

    body = [f'<p class="kicker">RoamingPigs research record</p><h1>{e(title)}</h1>',
            f'<p class="lede">Speed and energy per token for four local models on one AMD Ryzen AI MAX+ 395 mini PC, measured at the wall plug and at the chip, '
            f'{"on two software backends, " if SB else ""}with the plan and the expectations written down before the run.</p>',
            f'<p class="status">{e(status)}</p>', '<div class="stats">' + "".join(f"<div class='stat'><b>{a}</b><span>{b}</span></div>" for a, b in stats) + "</div>"]
    if SB:
        body += [f'<h2>What I found</h2>{findings(SA, SB, EV, la, lb)}']
    body += [f'<h2>Speed against context length</h2><figure>{figs["speed"]}<figcaption><strong>Decode speed.</strong> Tokens per second for each model as the prompt already in the cache grows from 64 to 32,768 tokens. The band is the lowest to highest of three repeats. All four panels share one scale.</figcaption></figure>',
             f'<h2>Energy per token</h2><figure>{figs["energy"]}<figcaption><strong>Joules per generated token, net of idle.</strong> Filled dots are the wall plug, hollow dots the chip\'s own sensor, each from 64 tokens of context (small dot) to 32k (large). The chip sensor always reads lower than the plug, because it sees only the chip.</figcaption></figure>',
             f'<h2>Where the watts go</h2><figure>{figs["watts"]}<figcaption><strong>While decoding (Vulkan, 64 tokens of context).</strong> The whole box draws about {idle["wall_w_median"]:.0f} W idle. The chip package accounts for most of what is added. The rest is everything else in the box that the chip sensor does not see.</figcaption></figure>',
             f'<h2>How one cell was measured</h2><figure>{figs["timeline"]}<figcaption><strong>One measured cell, raw.</strong> The plug is read about once a second and the chip sensor ten times a second. Each dip is the gap between one 512-token request and the next. Energy per token is the area above the idle line inside the window, divided by the tokens generated in it.</figcaption></figure>']
    if SB:
        body += [f'<h2>{lb} against {la}</h2><figure>{figs["ratio"]}<figcaption><strong>{lb} decode speed as a share of {la}.</strong> A plain number means the repeat ranges of the two backends do not overlap. A dotted outline means they overlap, so I make no claim.</figcaption></figure>']
    body += [f'<h2>Expectations written in advance</h2><figure>{figs["score"]}<figcaption>Each line was written before the run. "Wrong" is reported, not hidden.</figcaption></figure>',
             f'<h2>All numbers</h2>{table(SA, la)}']
    if SB:
        body += [f"<h3>{lb}</h3>", table(SB, lb)]
    body += ['<h2>What this does not show</h2><ul class="limits"><li>Anything about other hardware, other chips, discrete GPUs or other builds of <code>llama.cpp</code>.</li>'
             '<li>The accuracy of the wall watts. The plug is uncalibrated and reads whole watts. The chip sensor is what the chip reports about itself.</li>'
             '<li>Batched or concurrent serving. Everything here is one stream at a time.</li>'
             '<li>Quality of the output. Prompts are licence texts and the replies are not scored.</li>'
             '<li>That anyone outside this project has repeated it.</li></ul>',
             f'<h2>Reproduce or check</h2><p>Plan, code, raw wall and package power logs and every deviation from the plan: <a href="https://github.com/RoamingPigs/strix-halo-energy">github.com/RoamingPigs/strix-halo-energy</a>. Report built from commit <code>{e(git("rev-parse","--short","HEAD"))}</code>. Self-published by Cisco Caceres.</p>']
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(title)}</title><style>{CSS}</style></head><body><main class="wrap">{"".join(body)}</main></body></html>')
    out.write_text(page)
    drops = [100 * (1 - SA["cells"][f"{mk}@32768"]["tok_per_s"]["mean"] / SA["cells"][f"{mk}@64"]["tok_per_s"]["mean"]) for mk, _, _ in F.MODELS]
    cards = {"share-energy": (f"{min(jw):.1f} to {max(jw):.1f} joules per token", "Energy per generated token on one Strix Halo mini PC, wall plug, net of idle.", figs["energy"]),
             "share-speed": (f"Speed falls {min(drops):.0f} to {max(drops):.0f}% as context grows to 32k", "Decode speed for four local models, three repeats each.", figs["speed"])}
    if SB:
        rr = [SB["cells"][k]["tok_per_s"]["mean"] / SA["cells"][k]["tok_per_s"]["mean"] for k in SA["cells"] if k in SB["cells"]]
        cards["share-rocm"] = (f"ROCm was {100-max(rr)*100:.0f} to {100-min(rr)*100:.0f}% slower than Vulkan", "Decode speed on one Strix Halo mini PC, same models and prompts, three repeats each.", figs["ratio"])
    for name, (h, sub, fig) in cards.items():
        (out.parent / f"{name}.html").write_text(
            f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}body{{width:1200px;height:630px;margin:0;overflow:hidden;background:#f6f3ec}}'
            f'.card{{padding:34px 48px}}.card h1{{font-size:44px;margin:.2rem 0 .3rem}}.card p{{margin:0 0 .6rem;font:400 20px/1.3 Inter,system-ui,sans-serif;color:#3a362d}}'
            f'.card .fig{{background:#fffdf8;border:1px solid #d9d3c3;border-radius:8px;padding:10px 16px;height:372px}}.card .fig svg{{height:100%;width:100%}}'
            f'.foot{{position:absolute;bottom:18px;left:48px;right:48px;font:600 16px Inter,system-ui,sans-serif;color:#6b6558;display:flex;justify-content:space-between}}</style></head>'
            f'<body><div class="card"><p class="kicker">RoamingPigs research record</p><h1>{e(h)}</h1><p>{e(sub)}</p><div class="fig">{fig}</div></div>'
            f'<div class="foot"><span>roamingpigs.org</span><span>Self-published. Not peer reviewed. One machine.</span></div></body></html>')
    print("wrote", out, len(page) // 1024, "KB;", n_ex, "expectations")


if __name__ == "__main__":
    main()
