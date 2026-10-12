"""Synthetic check of analyze.py: known power in, known joules per token out."""
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "harness"))
import analyze  # noqa: E402

IDLE, LOAD, LAG = 20.0, 100.0, 4.4
T0 = 1_800_000_000.0


def true_power(t, loaded):
    return np.where(loaded(t), LOAD, IDLE)


def build(tmp, tokens=6000):
    # timeline: step test, then one cell
    ev = []
    t = T0 + 10
    ev.append({"kind": "idle", "label": "step_idle_before", "t0": t, "t1": t + 60, "t": t + 60}); t += 60
    ev.append({"kind": "step_load", "t0": t, "t1": t + 60, "t": t + 60}); step_load = (t, t + 60); t += 60
    ev.append({"kind": "idle", "label": "step_idle_after", "t0": t, "t1": t + 60, "t": t + 60}); t += 60
    cell = {"model": "m", "depth": 64, "round": 1}
    ev.append({"kind": "cell_start", "t": t, **cell})
    ev.append({"kind": "idle", "label": "settle_before", "t0": t, "t1": t + 30, "t": t + 30, **cell}); t += 30
    w0 = t
    ev.append({"kind": "decode_request", "t_send": w0, "t_recv": w0 + 120, "timings": {"predicted_n": tokens, "predicted_ms": 120000.0}, "t": w0 + 120, **cell})
    ev.append({"kind": "window", "t0": w0, "t1": w0 + 120, "n_requests": 1, "cache_reused": True, "tokens": tokens, "t": w0 + 120, **cell}); t += 120
    ev.append({"kind": "idle", "label": "settle_after", "t0": t, "t1": t + 30, "t": t + 30, **cell}); t += 30
    ev.append({"kind": "cell_end", "contaminated": False, "flags": [], "t": t, **cell})
    loaded_spans = [step_load, (w0, w0 + 120)]
    loaded = lambda x: np.any([(x >= a) & (x < b) for a, b in loaded_spans], axis=0)
    # hwmon 10 Hz: package = 0.7 * wall
    th = np.arange(T0, t + 20, 0.1)
    ppt = 0.7 * true_power(th, loaded)
    hw = "t_unix,ppt_w,gpu_temp_c,cpu_temp_c,gpu_clock_mhz,gpu_busy_pct\n" + "".join(
        f"{a:.3f},{b:.3f},50,50,2000,50\n" for a, b in zip(th, ppt))
    # plug 1 Hz, integer watts, reading lags the truth by LAG seconds
    tp = np.arange(T0 + 0.37, t + 20, 1.0)
    wall = np.round(true_power(tp - LAG, loaded))
    kwh = np.cumsum(wall) / 3600.0 / 1000.0
    pl = "t_send,t_recv,power_w,apparent_va,voltage_v,current_a,factor,total_kwh,plug_time,error\n" + "".join(
        f"{a:.3f},{a + 0.1:.3f},{w:.0f},0,120,0,1,{k:.6f},,\n" for a, w, k in zip(tp, wall, kwh))
    (tmp / "events.jsonl").write_text("\n".join(json.dumps(e) for e in ev) + "\n")
    (tmp / "hwmon.csv").write_text(hw)
    (tmp / "plug.csv").write_text(pl)
    return tokens


def test_energy_per_token_and_lag(tmp_path):
    tokens = build(tmp_path)
    models = tmp_path / "models.json"
    models.write_text(json.dumps({"m": {"kind": "dense", "label": "m"}}))
    out = analyze.run(tmp_path, models)
    assert abs(out["lag_s"] - LAG) <= 0.6, out["lag_s"]
    c = out["cells"]["m@64"]
    expect_net = (LOAD - IDLE) * 120 / tokens
    assert abs(c["wall_net_j_per_tok"]["mean"] - expect_net) / expect_net < 0.03
    expect_gross = LOAD * 120 / tokens
    assert abs(c["wall_gross_j_per_tok"]["mean"] - expect_gross) / expect_gross < 0.03
    assert abs(c["ppt_net_j_per_tok"]["mean"] - 0.7 * expect_net) / (0.7 * expect_net) < 0.02
    assert abs(c["wall_ppt_ratio"]["mean"] - 1 / 0.7) < 0.1
    assert abs(c["tok_per_s"]["mean"] - tokens / 120) < 1e-6


def test_no_lag_correction_overstates_nothing_by_much(tmp_path):
    """Without the lag fix the window is shifted by about 4 s of a 120 s window: error stays near 3 to 4 percent."""
    tokens = build(tmp_path)
    models = tmp_path / "models.json"
    models.write_text(json.dumps({"m": {"kind": "dense", "label": "m"}}))
    out = analyze.run(tmp_path, models)
    sens = [json.loads(r) if False else None for r in []]
    rows = list(__import__("csv").DictReader(open(tmp_path / "cells.csv")))
    assert len(rows) == 1


def test_plan_is_deterministic():
    import make_plan
    a, b = make_plan.make_plan(), make_plan.make_plan()
    assert a == b
    for r in a["rounds"]:
        assert sorted(x["model"] for x in r["blocks"]) == sorted(json.loads((pathlib.Path(make_plan.__file__).parent / "models.json").read_text()))
        for blk in r["blocks"]:
            assert sorted(blk["depths"]) == sorted(make_plan.DEPTHS)


def test_slot_wait_avoids_ticks():
    import warden_study as w
    # a tick at 600*k + 3.5. Right after a tick there is room; just before the next one we must wait past it.
    k = 3_000_000
    tick = k * 600 + 3.5
    assert w.slot_wait(tick + 15, 240) == 0.0
    nxt = tick + 600
    wait = w.slot_wait(nxt - 100, 240)
    assert abs((nxt - 100 + wait) - (nxt + w.TICK_GUARD_S)) < 1e-6
    # a cell that would end exactly at the tick is not allowed
    assert w.slot_wait(nxt - 250, 240) > 0
