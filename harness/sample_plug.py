#!/usr/bin/env python3
"""Poll a Tasmota smart plug about once a second and append to a CSV. Run on a machine other than the one measured.

Password from the environment variable named by --password-env (never on the command line).
Columns: t_send, t_recv (unix), power_w, apparent_va, voltage_v, current_a, factor, total_kwh, plug_time
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password-env", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--period", type=float, default=1.0)
    args = ap.parse_args()
    pw = os.environ[args.password_env]
    url = f"http://{args.host}/cm?user={urllib.parse.quote(args.user)}&password={urllib.parse.quote(pw)}&cmnd=Status%208"
    new = not os.path.exists(args.out)
    f = open(args.out, "a", newline="", buffering=1)
    w = csv.writer(f)
    if new:
        w.writerow(["t_send", "t_recv", "power_w", "apparent_va", "voltage_v", "current_a", "factor", "total_kwh", "plug_time", "error"])
    nxt = time.monotonic()
    while True:
        t_send = time.time()
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                sns = json.load(r)["StatusSNS"]
                t_recv = time.time()
                e = sns["ENERGY"]
                w.writerow([f"{t_send:.3f}", f"{t_recv:.3f}", e["Power"], e["ApparentPower"], e["Voltage"], e["Current"],
                            e["Factor"], e["Total"], sns.get("Time", ""), ""])
        except Exception as ex:
            w.writerow([f"{t_send:.3f}", f"{time.time():.3f}", "", "", "", "", "", "", "", type(ex).__name__])
        nxt += args.period
        time.sleep(max(0.0, nxt - time.monotonic()))


if __name__ == "__main__":
    sys.exit(main())
