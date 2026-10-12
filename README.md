# Strix Halo batch-1 energy per token

A plan-first measurement of decode speed and energy per token on one AMD Ryzen AI MAX+ 395 mini PC, for four models at four context depths, with raw wall-power and package-power logs published beside every result.

Self-published, not peer reviewed. Written by Cisco Caceres ([roamingpigs.org](https://roamingpigs.org/)).

- `PLAN.md` was pushed before the run. It fixes the models, flags, procedure, analyses and the expectations I wrote down first.
- `harness/` is the code: `warden_study.py` runs on the machine under test, `sample_plug.py` polls the smart plug from another machine, `analyze.py` does every pre-specified analysis, `make_plan.py` writes the seeded run order.
- `results/` (after the run) holds the raw logs, per-cell results and the report.
- `tests/` checks the analysis on synthetic power with a known answer, including that it fails when the plug-lag correction is removed.

## What this does not claim

No comparison with other hardware. The wall meter is an uncalibrated smart plug that reports integer watts. One machine, one build of `llama.cpp` (Vulkan), one stream at a time. See "What this study cannot show" in `PLAN.md`.

## Why it exists

My earlier published figures for this machine were partly formula-generated, and a "3.5 to 4.4 times lower energy per token than an H100" claim compared unlike things. That claim is withdrawn. Corrections are logged at [roamingpigs.org/corrections](https://roamingpigs.org/corrections/).

## Licence

Code and text: Apache-2.0.
