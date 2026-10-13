# Strix Halo batch-1 energy per token

A plan-first measurement of decode speed and energy per token on one AMD Ryzen AI MAX+ 395 mini PC, for four models at four context depths, on two software backends (Vulkan and ROCm), with raw wall-power and package-power logs published beside every result.

The short version is in [`RESULTS.md`](RESULTS.md). A readable report with charts is `report/report.html` (PDF: `report/report.pdf`). The same study is on the web at [roamingpigs.org/studies/strix-halo-energy](https://roamingpigs.org/studies/strix-halo-energy/).

Self-published, not peer reviewed. Written by Cisco Caceres ([roamingpigs.org](https://roamingpigs.org/)).

- `PLAN.md` was pushed before study 1 (Vulkan). `PLAN-3.md` was pushed before the paired Vulkan and ROCm run. Each fixes the models, flags, procedure, analyses and the expectations I wrote down first. `PLAN-ROCM.md` was superseded by `PLAN-3.md` and is kept for the record.
- `harness/` is the code: `warden_study.py` runs on the machine under test, `sample_plug.py` polls the smart plug from another machine, `analyze.py` does every pre-specified analysis, `make_plan.py` writes the seeded run order.
- `results/` holds the raw logs and per-cell results: `merged` is study 1 and `paired4` is the paired run. Aborted starts are kept in `results/*-aborted/` and not used. `harness/evaluate_plan3.py` scores the paired run against its plan.
- `report/` builds the report, the charts and the site export from the results.
- `tests/` checks the analysis on synthetic power with a known answer, including that it fails when the plug-lag correction is removed.

## What this does not claim

No comparison with other hardware. The wall meter is an uncalibrated smart plug that reports integer watts. One machine, one build of `llama.cpp` (b10970, built for Vulkan and for ROCm), one stream at a time. No one outside this project has repeated it. See "What this study cannot show" in `PLAN.md`.

## Why it exists

My earlier published figures for this machine were partly formula-generated, and a "3.5 to 4.4 times lower energy per token than an H100" claim compared unlike things. That claim is withdrawn. Corrections are logged at [roamingpigs.org/corrections](https://roamingpigs.org/corrections/).

## Licence

Code and text: Apache-2.0.

Results: see `RESULTS.md`. Deviations from the plan: `DEVIATIONS.md`.
