#!/usr/bin/env python3
"""Draws the study's figures as self-contained inline SVG from the analysis output. No JavaScript, no libraries.

Every figure carries <title> and <desc> with its numbers, and takes its colours from CSS variables with light-page
defaults, so a host page can re-theme it (the sites set --f-* on a wrapper).

usage: figures.py OUT_DIR SUMMARY_A.json [SUMMARY_B.json]   A = first backend, B = second (optional)
"""
import json
import pathlib
import sys
from html import escape as e

MODELS = [  # key, label, short label  (size and kind only: the files themselves are named in the report table)
    ("qwen35-9b-q4km", "9B dense, 4-bit", "9B dense"),
    ("gemma4-12b-q4", "12B dense, 4-bit", "12B dense"),
    ("gemma4-26b-a4b-q4", "26B mixture, 4B active, 4-bit", "26B mixture"),
    ("qwen36-35b-a3b-q8", "35B mixture, 3B active, 8-bit", "35B mixture"),
]
DEPTHS = [64, 4096, 16384, 32768]
DEPTH_LABEL = {64: "64", 4096: "4k", 16384: "16k", 32768: "32k"}

STYLE = """<style>
.sh text{font-family:var(--f-sans,Inter,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif);fill:var(--f-ink2,#3a362d);font-size:12.5px}
.sh .t{fill:var(--f-ink,#15130f);font-weight:600}.sh .m{fill:var(--f-mut,#6b6558);font-size:11.5px}
.sh .v{font-family:var(--f-mono,ui-monospace,Menlo,Consolas,monospace);fill:var(--f-ink,#15130f);font-size:12px;font-weight:500}
.sh .big{font-size:26px;font-weight:650;fill:var(--f-ink,#15130f)}
.sh .g{stroke:var(--f-rule,#d9d3c3);stroke-width:1;fill:none}.sh .ax{stroke:var(--f-rule2,#b9b19b);stroke-width:1;fill:none}
.sh .a{stroke:var(--f-a,#1a47c9);fill:none;stroke-width:2.25;stroke-linejoin:round;stroke-linecap:round}
.sh .b{stroke:var(--f-b,#c2410c);fill:none;stroke-width:2.25;stroke-linejoin:round;stroke-linecap:round}
.sh .af{fill:var(--f-a,#1a47c9)}.sh .bf{fill:var(--f-b,#c2410c)}
.sh .aw{fill:var(--f-a,#1a47c9);opacity:.16}.sh .bw{fill:var(--f-b,#c2410c);opacity:.16}
.sh .hollow{fill:var(--f-bg,#fffdf8);stroke-width:2}
.sh .idle{stroke:var(--f-mut,#6b6558);stroke-width:1.25;stroke-dasharray:4 3}
.sh .win{fill:var(--f-ink,#15130f);opacity:.06}
.sh .ok{fill:var(--f-ok,#0b6b4d)}.sh .bad{fill:var(--f-bad,#a32020)}
.sh .hm{stroke:var(--f-mut,#6b6558)}.sh .ha{stroke:var(--f-a,#1a47c9)}.sh .hb{stroke:var(--f-b,#c2410c)}.sh .lo{opacity:.45}
.sh .wf-idle{fill:var(--f-rule2,#b9b19b)}.sh .wf-a{fill:var(--f-a,#1a47c9)}.sh .wf-b{fill:var(--f-b,#c2410c)}
.sh .hm-a{fill:var(--f-a,#1a47c9)}.sh .hm-b{fill:var(--f-b,#c2410c)}.sh .hm-dash{fill:none;stroke:var(--f-mut,#6b6558);stroke-dasharray:2 3}
.sh .op1{opacity:.1}.sh .op2{opacity:.2}.sh .op3{opacity:.3}.sh .op4{opacity:.4}.sh .op5{opacity:.5}.sh .op6{opacity:.6}.sh .op7{opacity:.7}.sh .op8{opacity:.8}.sh .op9{opacity:.9}
.sh .chip{fill:var(--f-chip,#e1f1ea)}.sh .chipb{fill:var(--f-chipb,#f6dede)}
</style>"""


CLASS_ONLY = False   # True: no <style> block and no style attributes, for pages with a strict Content-Security-Policy


def svg(w, h, uid, title, desc, body):
    return (f'<svg class="sh" viewBox="0 0 {w} {h}" width="100%" role="img" aria-labelledby="{uid}-t {uid}-d" '
            f'xmlns="http://www.w3.org/2000/svg">{"" if CLASS_ONLY else STYLE}<title id="{uid}-t">{e(title)}</title>'
            f'<desc id="{uid}-d">{e(desc)}</desc>{body}</svg>')


def nice_max(v):
    cands = sorted(step * mag for step in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8) for mag in (0.1, 1, 10, 100, 1000))
    return next(c for c in cands if c >= v * 1.04)


def ticks(vmax, n=4):
    return [vmax * i / n for i in range(n + 1)]


def cell(S, key):
    return S["cells"].get(key)


def speed_vs_depth(SA, SB, la, lb):
    """Small multiples: tokens per second against context length, one panel per model, repeat range as a band."""
    pw, ph, gx, gy, left, top = 300, 170, 40, 58, 46, 84
    W = left + 2 * pw + gx + 20
    H = top + 2 * ph + gy + 30
    out = [f'<text class="m" x="{left}" y="50">Tokens per second, by context length (tokens already in the cache)</text>']
    # legend
    out.append(f'<line class="a" x1="{left}" y1="24" x2="{left+26}" y2="24"/><text x="{left+32}" y="28">{e(la)}</text>')
    if SB:
        out.append(f'<line class="b" x1="{left+130}" y1="24" x2="{left+156}" y2="24"/><text x="{left+162}" y="28">{e(lb)}</text>')
    gmax = nice_max(max(cell(S, f"{mk}@{d}")["tok_per_s"]["max"] for S in (SA, SB) if S for mk, _, _ in MODELS for d in DEPTHS if cell(S, f"{mk}@{d}")))
    desc = []
    for i, (mk, lab, short) in enumerate(MODELS):
        px = left + (i % 2) * (pw + gx)
        py = top + (i // 2) * (ph + gy)
        vals = [cell(S, f"{mk}@{d}") for S in (SA, SB) if S for d in DEPTHS]
        vmax = gmax
        out.append(f'<text class="t" x="{px}" y="{py-12}">{e(lab)}</text>')
        for g in ticks(vmax):
            y = py + ph - g / vmax * ph
            out.append(f'<line class="g" x1="{px}" y1="{y:.1f}" x2="{px+pw}" y2="{y:.1f}"/><text class="m" x="{px-6}" y="{y+4:.1f}" text-anchor="end">{g:g}</text>')
        xs = [px + 24 + j * (pw - 48) / 3 for j in range(4)]
        for j, d in enumerate(DEPTHS):
            out.append(f'<text class="m" x="{xs[j]:.1f}" y="{py+ph+16}" text-anchor="middle">{DEPTH_LABEL[d]}</text>')
        out.append(f'<line class="ax" x1="{px}" y1="{py+ph}" x2="{px+pw}" y2="{py+ph}"/>')
        for S, cls, band in ((SA, "a", "aw"), (SB, "b", "bw")):
            if not S:
                continue
            pts = []
            for j, d in enumerate(DEPTHS):
                c = cell(S, f"{mk}@{d}")
                if c:
                    pts.append((xs[j], py + ph - c["tok_per_s"]["mean"] / vmax * ph,
                                py + ph - c["tok_per_s"]["min"] / vmax * ph, py + ph - c["tok_per_s"]["max"] / vmax * ph,
                                c["tok_per_s"]["mean"], c["tok_per_s"]["n"]))
            if len(pts) > 1:
                top_ = " ".join(f"{p[0]:.1f},{p[3]-2:.1f}" for p in pts)
                bot_ = " ".join(f"{p[0]:.1f},{p[2]+2:.1f}" for p in reversed(pts))
                out.append(f'<polygon class="{band}" points="{top_} {bot_}"/>')
                out.append(f'<polyline class="{cls}" points="{" ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in pts)}"/>')
            for p in pts:
                out.append(f'<circle class="{cls[0]}f" cx="{p[0]:.1f}" cy="{p[1]:.1f}" r="3.5"/>')
            if pts:
                dy = -9 if S is SA else 17   # first backend's numbers above its line, second backend's below
                out.append(f'<text class="v" x="{pts[0][0]:.1f}" y="{pts[0][1]+dy:.1f}" text-anchor="middle">{pts[0][4]:.0f}</text>')
                out.append(f'<text class="v" x="{pts[-1][0]:.1f}" y="{pts[-1][1]+dy:.1f}" text-anchor="middle">{pts[-1][4]:.0f}</text>')
                desc.append(f"{short}, {la if S is SA else lb}: " + ", ".join(f"{DEPTH_LABEL[d]} {cell(S, f'{mk}@{d}')['tok_per_s']['mean']:.1f}" for d in DEPTHS if cell(S, f"{mk}@{d}")))
    return svg(W, H, "f-speed", "Decode speed against context length", "Tokens per second by model and context length. " + "; ".join(desc), "".join(out))


def energy_ladder(SA, SB, la, lb):
    """Energy per generated token, wall (filled) and package (hollow), shallow to deep context joined by a line."""
    row, top, left, right = 74, 66, 190, 70
    W, H = 700, top + row * len(MODELS) + 44
    allv = [cell(S, f"{mk}@{d}")[k]["max"] for S in (SA, SB) if S for mk, _, _ in MODELS for d in DEPTHS
            if cell(S, f"{mk}@{d}") for k in ("wall_net_j_per_tok",)]
    vmax = nice_max(max(allv))
    x0, x1 = left, W - right
    sc = (x1 - x0) / vmax
    out = [f'<text class="m" x="{x1-0}" y="{H-2}" text-anchor="end">Joules per generated token, net of idle</text><line class="a" x1="{x0}" y1="22" x2="{x0+26}" y2="22"/><text x="{x0+32}" y="26">{e(la)}</text>']
    if SB:
        out.append(f'<line class="b" x1="{x0+110}" y1="22" x2="{x0+136}" y2="22"/><text x="{x0+142}" y="26">{e(lb)}</text>')
    out.append(f'<circle class="af" cx="{x0+250}" cy="22" r="5"/><text x="{x0+260}" y="26">wall plug</text><circle class="hollow hm" cx="{x0+342}" cy="22" r="5"/><text x="{x0+352}" y="26">chip package</text>')
    for g in ticks(vmax, 5):
        x = x0 + g * sc
        out.append(f'<line class="g" x1="{x:.1f}" y1="{top-14}" x2="{x:.1f}" y2="{H-34}"/><text class="m" x="{x:.1f}" y="{H-16}" text-anchor="middle">{g:g}</text>')
    desc = []
    for i, (mk, lab, short) in enumerate(MODELS):
        y = top + i * row + 14
        out.append(f'<text class="t" x="{x0-12}" y="{y+(6 if not SB else 14)}" text-anchor="end">{e(short)}</text>')
        rows_ = [(SA, "a", la)] + ([(SB, "b", lb)] if SB else [])
        for ri, (S, cls, nm) in enumerate(rows_):
            pts = [(d, cell(S, f"{mk}@{d}")) for d in DEPTHS if cell(S, f"{mk}@{d}")]
            if not pts:
                continue
            for kind, key in (("wall", "wall_net_j_per_tok"), ("pkg", "ppt_net_j_per_tok")):
                yy = y + ri * (28 if SB else 0) + (0 if kind == "wall" else 13)
                xs_ = [x0 + c[key]["mean"] * sc for _, c in pts]
                out.append(f'<line class="{cls}" x1="{xs_[0]:.1f}" y1="{yy}" x2="{xs_[-1]:.1f}" y2="{yy}" />'.replace('class="' + cls + '"', 'class="' + cls + ('' if kind == "wall" else ' lo') + '"'))
                for xv, (d, c) in zip(xs_, pts):
                    r = 2.6 + 1.0 * DEPTHS.index(d)
                    if kind == "wall":
                        out.append(f'<circle class="{cls[0]}f" cx="{xv:.1f}" cy="{yy}" r="{r:.1f}"><title>{short}, {nm}, {DEPTH_LABEL[d]}: wall {c[key]["mean"]:.2f} J/token</title></circle>')
                    else:
                        out.append(f'<circle class="hollow h{cls}" cx="{xv:.1f}" cy="{yy}" r="{r:.1f}"><title>{short}, {nm}, {DEPTH_LABEL[d]}: package {c[key]["mean"]:.2f} J/token</title></circle>')
            wx = x0 + pts[-1][1]["wall_net_j_per_tok"]["mean"] * sc
            out.append(f'<text class="v" x="{wx+12:.1f}" y="{y + ri * 28 + 4}">{pts[-1][1]["wall_net_j_per_tok"]["mean"]:.2f}</text>')
            desc.append(f"{short}, {la if S is SA else lb}: wall net " + ", ".join(f"{DEPTH_LABEL[d]} {c['wall_net_j_per_tok']['mean']:.2f}" for d, c in pts))
    return svg(W, H, "f-energy", "Energy per generated token", "Joules per token, wall net of idle. " + "; ".join(desc), "".join(out))


def where_watts_go(S, label):
    """At 64 tokens of context: idle floor, extra at the package, extra elsewhere in the box (wall minus package)."""
    row, top, left, right = 50, 52, 120, 70
    W, H = 700, top + row * len(MODELS) + 40
    idle = S["idle"]["bare_idle_block"] if "bare_idle_block" in S["idle"] else next(iter(S["idle"].values()))
    idle_w = idle["wall_w_median"]
    idle_p = idle["ppt_w_median"]
    vmax = nice_max(max(cell(S, f"{mk}@64")["wall_mean_w"]["max"] for mk, _, _ in MODELS))
    x0, x1 = left, W - right
    sc = (x1 - x0) / vmax
    out = []
    lg = [("wf-idle", f"Idle ({idle_w:.0f} W)"), ("wf-a", "Added at the chip"), ("wf-b", "Added elsewhere in the box")]
    lg = [lg[0], lg[1], lg[2]]
    lx = x0
    for col, txt in lg:
        out.append(f'<rect x="{lx}" y="14" width="12" height="12" rx="2" class="{col}"/><text x="{lx+18}" y="25">{e(txt)}</text>')
        lx += 18 + 6.9 * len(txt) + 16
    for g in ticks(vmax, 5):
        x = x0 + g * sc
        out.append(f'<line class="g" x1="{x:.1f}" y1="{top-6}" x2="{x:.1f}" y2="{H-34}"/><text class="m" x="{x:.1f}" y="{H-16}" text-anchor="middle">{g:g} W</text>')
    desc = []
    for i, (mk, lab, short) in enumerate(MODELS):
        c = cell(S, f"{mk}@64")
        y = top + i * row + 4
        wall, pkg = c["wall_mean_w"]["mean"], c["ppt_mean_w"]["mean"]
        add_pkg = max(pkg - idle_p, 0)
        rest = max(wall - idle_w - add_pkg, 0)
        out.append(f'<text class="t" x="{x0-12}" y="{y+22}" text-anchor="end">{e(short)}</text>')
        xx = x0
        for w_, col in ((idle_w, "wf-idle"), (add_pkg, "wf-a"), (rest, "wf-b")):
            out.append(f'<rect x="{xx:.1f}" y="{y+6}" width="{w_*sc:.1f}" height="26" class="{col}"/>')
            xx += w_ * sc
        out.append(f'<text class="v" x="{xx+8:.1f}" y="{y+24}">{wall:.0f} W</text>')
        desc.append(f"{short}: {wall:.0f} W at the wall, of which idle {idle_w:.0f}, extra at the package {add_pkg:.0f}, elsewhere {rest:.0f}")
    return svg(W, H, "f-watts", "Where the wall watts go", "; ".join(desc), "".join(out))


def held_flags(S):
    """(label, held) for each expectation in a summary."""
    res = []
    for k, v in S["expectations"].items():
        holds = v.get("holds", v.get("in_range"))
        if k.startswith("E2"):
            holds = v["in_range"] and v["moe_lower"]
        res.append((k, bool(holds)))
    return res


def scorecard(S, rows_label, items=None, detail=None):
    """Each expectation written in advance, whether it held, and the number behind it.
    items: optional list of (label, held) to use instead of a summary's E1 to E6."""
    items = items if items is not None else held_flags(S)
    detail = detail or {}
    row = 54 if detail else 44
    W, H = 700, 8 + row * len(items)
    out = []
    for i, (k, ok) in enumerate(items):
        y = i * row
        tag, _, txt = k.partition(" ")
        out.append(f'<rect class="{"chip" if ok else "chipb"}" x="0" y="{y}" width="640" height="{row-8}" rx="4"/>')
        out.append(f'<text class="t" x="14" y="{y+22}">{e(tag)}</text><text x="52" y="{y+22}">{e(txt)}</text>')
        if tag in detail:
            out.append(f'<text class="m" x="52" y="{y+36}">{e(detail[tag])}</text>')
        out.append(f'<text class="{"ok" if ok else "bad"} t" x="626" y="{y+22}" text-anchor="end">{"held" if ok else "wrong"}</text>')
    return svg(W, H, "f-score", "Expectations written in advance", "; ".join(f"{k}: {'held' if ok else 'wrong'}" for k, ok in items), "".join(out))


def ratio_heatmap(SA, SB, la, lb):
    """B over A decode speed per model and depth. Hatched where the repeat ranges overlap (no claim)."""
    cw, ch, left, top = 112, 54, 160, 40
    W, H = left + cw * 4 + 16, top + ch * len(MODELS) + 8
    out = []
    for j, d in enumerate(DEPTHS):
        out.append(f'<text class="t" x="{left+j*cw+cw/2}" y="{top-14}" text-anchor="middle">{DEPTH_LABEL[d]}</text>')
    desc = []
    for i, (mk, lab, short) in enumerate(MODELS):
        out.append(f'<text class="t" x="{left-12}" y="{top+i*ch+ch/2+4}" text-anchor="end">{e(short)}</text>')
        for j, d in enumerate(DEPTHS):
            a, b = cell(SA, f"{mk}@{d}"), cell(SB, f"{mk}@{d}")
            if not a or not b:
                continue
            r = b["tok_per_s"]["mean"] / a["tok_per_s"]["mean"]
            real = b["tok_per_s"]["min"] > a["tok_per_s"]["max"] or b["tok_per_s"]["max"] < a["tok_per_s"]["min"]
            col = "hm-b" if r < 1 else "hm-a"
            op = max(1, min(9, round((0.12 + abs(1 - r) * 2.2) * 10)))   # opacity class op1..op9, one per 0.1
            x, y = left + j * cw, top + i * ch
            out.append(f'<rect x="{x+2}" y="{y+2}" width="{cw-4}" height="{ch-4}" rx="4" class="{col} op{op}"/>')
            if not real:
                out.append(f'<rect x="{x+2}" y="{y+2}" width="{cw-4}" height="{ch-4}" rx="4" class="hm-dash"/>')
            out.append(f'<text class="v" x="{x+cw/2}" y="{y+ch/2+5}" text-anchor="middle">{r*100:.0f}%</text>')
            desc.append(f"{short} {DEPTH_LABEL[d]}: {r*100:.0f}% ({'real' if real else 'overlap'})")
    return svg(W, H, "f-ratio", f"{lb} against {la}", "Decode speed ratio. " + "; ".join(desc), "".join(out))


def power_timeline(raw, model, depth, rnd, backend=None, label=""):
    """One measured cell from the raw logs: wall watts (plug) and package watts, the idle baseline and the window."""
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "harness"))
    import numpy as np
    import analyze
    raw = pathlib.Path(raw)
    ev = analyze.load_events(raw / "events.jsonl")
    cells = [x for x in ev if x.get("model") == model and x.get("depth") == depth and x.get("round") == rnd
             and (backend is None or x.get("backend") == backend)]
    t_start = [x for x in cells if x["kind"] == "cell_start"][-1]["t"]
    win = [x for x in cells if x["kind"] == "window" and x["t"] > t_start][0]
    bef = [x for x in cells if x["kind"] == "idle" and x["label"] == "settle_before" and x["t0"] > t_start][0]
    aft = [x for x in cells if x["kind"] == "idle" and x["label"] == "settle_after" and x["t0"] > t_start][0]
    plug = analyze.load_csv(raw / "plug.csv", ["t_send", "t_recv", "power_w", "apparent_va", "voltage_v", "current_a", "factor", "total_kwh"])
    hw = analyze.load_csv(raw / "hwmon.csv", ["t_unix", "ppt_w", "gpu_temp_c", "cpu_temp_c", "gpu_clock_mhz", "gpu_busy_pct"])
    t0, t1 = bef["t0"] + 5, aft["t1"] - 5
    m = (plug[:, 0] >= t0) & (plug[:, 0] <= t1)
    tw, ww = (plug[m, 0] + plug[m, 1]) / 2 - t0, plug[m, 2]
    mh = (hw[:, 0] >= t0) & (hw[:, 0] <= t1)
    hx, hy = hw[mh, 0] - t0, hw[mh, 1]
    k = max(len(hx) // 400, 1)   # 1 s means keep the file small
    hx, hy = hx[: len(hx) // k * k].reshape(-1, k).mean(axis=1), hy[: len(hy) // k * k].reshape(-1, k).mean(axis=1)
    left, top, W, H = 56, 54, 700, 330
    pw, ph = W - left - 24, H - top - 52
    xmax, ymax = t1 - t0, nice_max(float(ww.max()))
    X = lambda t: left + t / xmax * pw
    Y = lambda v: top + ph - v / ymax * ph
    idle_w = 0.5 * (float(np.mean(ww[(tw + t0 > bef["t1"] - 20) & (tw + t0 <= bef["t1"])])) + float(np.mean(ww[(tw + t0 > aft["t0"] + 10) & (tw + t0 <= aft["t0"] + 30)])))
    out = [f'<rect class="win" x="{X(win["t0"]-t0):.1f}" y="{top}" width="{X(win["t1"]-t0)-X(win["t0"]-t0):.1f}" height="{ph}"/>']
    for g in ticks(ymax, 5):
        out.append(f'<line class="g" x1="{left}" y1="{Y(g):.1f}" x2="{left+pw}" y2="{Y(g):.1f}"/><text class="m" x="{left-6}" y="{Y(g)+4:.1f}" text-anchor="end">{g:g}</text>')
    for tt in range(0, int(xmax) + 1, 60):
        out.append(f'<text class="m" x="{X(tt):.1f}" y="{top+ph+16}" text-anchor="middle">{tt} s</text>')
    out.append(f'<polyline class="a" points="{" ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in zip(tw, ww))}"/>')
    out.append(f'<polyline class="b" points="{" ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in zip(hx, hy))}"/>')
    out.append(f'<line class="idle" x1="{left}" y1="{Y(idle_w):.1f}" x2="{left+pw}" y2="{Y(idle_w):.1f}"/>')
    out.append(f'<text class="m" x="{left+6}" y="{Y(idle_w)-6:.1f}">idle baseline {idle_w:.0f} W</text>')
    out.append(f'<text class="m" x="{(X(win["t0"]-t0)+X(win["t1"]-t0))/2:.1f}" y="{top+14}" text-anchor="middle">measured window</text>')
    out.append(f'<line class="a" x1="{left}" y1="22" x2="{left+26}" y2="22"/><text x="{left+32}" y="26">wall plug (whole box)</text><line class="b" x1="{left+190}" y1="22" x2="{left+216}" y2="22"/><text x="{left+222}" y="26">chip package sensor</text>')
    out.append(f'<text class="m" x="{left+pw}" y="{H-4}" text-anchor="end">Watts against time. Net energy = area above the dashed line, inside the window, divided by tokens generated.</text>')
    short = next(sh for k_, _, sh in MODELS if k_ == model)
    return svg(W, H, "f-timeline", f"Power during one measured cell: {short}, {DEPTH_LABEL[depth]} context",
               f"Wall power and package power over {xmax:.0f} seconds; idle baseline {idle_w:.0f} W; {label}", "".join(out))


def main():
    out = pathlib.Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    args = [a for a in sys.argv[2:] if not a.startswith("--")]
    SA = json.load(open(args[0]))
    SB = json.load(open(args[1])) if len(args) > 1 else None
    la, lb = ("Vulkan", "ROCm")
    files = {"speed-vs-depth": speed_vs_depth(SA, SB, la, lb), "energy-per-token": energy_ladder(SA, SB, la, lb),
             "where-watts-go": where_watts_go(SA, la), "scorecard": scorecard(SA, f"Study on the {la} backend")}
    raw = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--raw=")), None)
    if raw:
        files["power-timeline"] = power_timeline(raw, "gemma4-26b-a4b-q4", 4096, 1, None)
    if SB:
        files["ratio"] = ratio_heatmap(SA, SB, la, lb)
        files["where-watts-go-rocm"] = where_watts_go(SB, lb)
    for k, v in files.items():
        (out / f"{k}.svg").write_text(v)
    print("wrote", ", ".join(files))


if __name__ == "__main__":
    main()
