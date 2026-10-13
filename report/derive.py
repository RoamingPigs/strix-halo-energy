"""Sentences and table rows computed from the analysis summaries, shared by the report page and the site exports."""
import figures as F


def _side(SA, SB, k, m):
    a, b = SA["cells"][k][m], SB["cells"][k][m]
    return "higher" if b["min"] > a["max"] else "lower" if b["max"] < a["min"] else "overlap"


def findings(SA, SB, EV, la="Vulkan", lb="ROCm"):
    """[(label, plain sentence)]. Direction is claimed only where the repeat ranges do not overlap."""
    keys = [f"{mk}@{d}" for mk, _, _ in F.MODELS for d in F.DEPTHS if f"{mk}@{d}" in SA["cells"] and f"{mk}@{d}" in SB["cells"]]
    sp = [SB["cells"][k]["tok_per_s"]["mean"] / SA["cells"][k]["tok_per_s"]["mean"] for k in keys]
    lower = sum(1 for k in keys if _side(SA, SB, k, "tok_per_s") == "lower")
    out = [("Speed", f"{lb} decoded more slowly than {la} in {lower} of {len(keys)} cells, by {100 - max(sp) * 100:.0f} to {100 - min(sp) * 100:.0f}%, "
                     f"and the repeat ranges of the two backends do not overlap in those cells. It was never faster.")]
    for mk, _, short in F.MODELS:
        ks = [f"{mk}@{d}" for d in F.DEPTHS if f"{mk}@{d}" in keys]
        r = [SB["cells"][k]["wall_net_j_per_tok"]["mean"] / SA["cells"][k]["wall_net_j_per_tok"]["mean"] for k in ks]
        dirs = {_side(SA, SB, k, "wall_net_j_per_tok") for k in ks}
        word = "less" if dirs == {"lower"} else "more" if dirs == {"higher"} else "about the same (the repeat ranges overlap in some cells)"
        out.append((f"Energy, {short}", f"{lb} used {word} energy per token than {la}: {min(r) * 100 - 100:+.0f} to {max(r) * 100 - 100:+.0f}% "
                                         f"across the four context lengths (wall plug, net of idle)."))
    if EV:
        out.append(("Repeatability", f"{la} on the newer kernel, on another day, matched study 1 within {EV['P1']['max_abs_pct']}% in every one of the "
                                     f"{len(keys)} cells. Idle power was {EV['P4']['vulkan_median_w'][0]:g} W against {EV['P4']['study1_median_w'][0]:g} W."))
    return out


def table(S):
    """Rows for the numbers table: label, context label and the means."""
    lab = {k: l for k, l, _ in F.MODELS}
    rows = []
    for mk, _, _ in F.MODELS:
        for d in F.DEPTHS:
            c = S["cells"].get(f"{mk}@{d}")
            if c:
                rows.append({"model": lab[mk], "context": F.DEPTH_LABEL[d], "tok_s": round(c["tok_per_s"]["mean"], 1),
                             "wall_w": round(c["wall_mean_w"]["mean"]), "pkg_w": round(c["ppt_mean_w"]["mean"]),
                             "wall_j": round(c["wall_net_j_per_tok"]["mean"], 2), "pkg_j": round(c["ppt_net_j_per_tok"]["mean"], 2),
                             "n": c["tok_per_s"]["n"]})
    return rows
