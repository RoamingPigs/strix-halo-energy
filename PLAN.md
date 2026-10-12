# Analysis plan: batch-1 energy per token on one Strix Halo mini PC

Author: Cisco Caceres. Self-published, not peer reviewed. Written 2026-10-12, before the measured run.

This plan is pushed to this repository before the run starts. The push time is recorded by GitHub, and every report that uses the results names the commit that holds this file. It is a dated plan, not a registered one: no third-party registry holds a copy.

## Why this study

I published numbers about this machine before measuring it properly. The energy ledger on roamingpigs.org says most of its benchmark rows and its memory-bandwidth curve are formula-generated, and the datacenter-GPU side of its comparison is a scenario, not a measurement. A review found that my "3.5 to 4.4 times lower energy per token than an H100" claim compared wall power with GPU-only power, 4-bit models with full-precision ones, and batch 1 with datacenter serving. I am withdrawing that claim. This study replaces it with measurements I can defend, on one machine, and makes no comparison with other hardware.

What is already public, and not claimed as new here: sustained memory streaming of about 215 GB/s on this chip, decode being memory-bandwidth bound, and Vulkan versus ROCm comparisons in llama.cpp. What I think has not been published, and could not find in searches on 2026-10-12: repeated batch-1 joules per token for several models at several context depths, with raw wall and package power logs published beside them.

## The machine

One mini PC, called warden: AMD Ryzen AI MAX+ 395 (Strix Halo), Radeon 8060S, 128 GB LPDDR5X-8000 (256-bit), Ubuntu 26.04.1, Linux 7.0.0-34-generic, Mesa 26.0.8 (RADV), kernel command line `amd_iommu=off ttm.pages_limit=31457280 amdgpu.gttsize=131072 amdgpu.cwsr_enable=0`, CPU governor `performance`. Software: `llama.cpp` build b10970, Vulkan backend (the ROCm build on the machine finds no HIP device, because no ROCm runtime is installed, so ROCm is not tested).

## Fixed inputs

| Item | Value |
|---|---|
| Models | Four GGUF files already on the machine: Qwen3.5-9B Q4_K_M (dense), gemma-4-12B-it QAT Q4 (dense), gemma-4-26B-A4B-it QAT Q4 (mixture of experts), Qwen3.6-35B-A3B Q8_0 (mixture of experts). SHA-256 of each file is recorded in the results. |
| Backend and flags | `llama-server`, `-ngl 99 -c 36864 -np 1 -fa on --no-context-shift`, KV cache at the default f16, greedy decoding (`temperature 0`), `ignore_eos`. |
| Context depths | 64, 4,096, 16,384 and 32,768 tokens of prompt already in the cache, then 512 tokens generated per request. |
| Prompt text | The Debian licence texts in `/usr/share/common-licenses` concatenated in file-name order, cut to the depth in tokens by the model's own tokenizer. |
| Repeats | 3 rounds. In each round the order of models, and of depths within a model, is a seeded shuffle (seed 20261012, `harness/make_plan.py`). |
| Window | Decode requests are repeated back to back on the cached prompt until at least 120 s of decoding has passed. The measured window is from the first request's send time to the last request's receive time. |
| Wall power | The Tasmota smart plug on the machine (Tasmota 15.4.0, integer watts, cumulative energy to 1 Wh), polled about once a second. Uncalibrated: I have no second reference meter. |
| Package power | `hwmon5/power1_input` (the chip's reported package power, labelled PPT), read 10 times a second, with temperature and clock. |
| Hardware | One machine. Ambient temperature is not controlled and is not recorded except through the chip's own temperature sensors. |

## Procedure for each cell (model, depth)

1. Load the model once per block with `llama-server`. Wait 60 s, idle, with the model loaded ("loaded idle").
2. For each depth in the planned order: send the prompt once with `n_predict` 1 to fill the cache (untimed). Wait 30 s idle. Run the decode window. Wait 30 s idle.
3. Unload the model and wait 120 s idle ("bare idle") before the next model.
4. Before the first block and after the last, record 5 minutes of bare idle. At the start, also run a load step (60 s idle, 60 s decode, 60 s idle) to estimate the smart plug's response lag.

Guards: other programs share this machine. During each cell the harness checks every 5 s for any other process above 10% of a core, and after each cell it counts the generation, chat and embedding requests that `ollama` served in that cell's time range, from its journal. A cell with either is marked contaminated and is repeated once at the end. A model merely sitting loaded in `ollama` is logged but does not count, because it does not draw measurable power. Another host on the network sends one tiny `ollama` request at about 3.5 s past every tenth minute (found in the journal on 2026-10-12, before this plan). The harness therefore starts each cell only when the cell can end before the next such request, and otherwise idles until just after it; those waits are logged. Each decode request also re-evaluates about 4 prompt tokens (about 0.28 s of the 13 s), so the window power includes that small non-decode share. Tokens per second are computed from the server's decode time only, and energy per token from the whole window; both are reported. A cell where the chip temperature reaches 95 C is marked throttled and reported, not dropped.

If a model does not reuse the cached prompt between requests (the second request's `prompt_n` above 8), that model's cells switch to one long request sized to about 100 s, and the report says which models did.

## Pre-specified analyses

- **S1. Idle.** Median and interquartile range of wall watts and package watts in bare idle and in loaded idle, per model.
- **S2. Speed.** Decode tokens per second per cell, from the server's own timings: mean, standard deviation and range over the three repeats.
- **S3. Energy.** Joules per generated token per cell, in four forms: wall gross, wall net of idle, package gross, package net of idle. Net subtracts the mean of the idle power in the 20 s before and the 20 s after the window, times the window length. Wall power is shifted by the plug's lag estimated from the load step; results with no shift and with the shift plus or minus 2 s are given as a sensitivity check.
- **S4. Wall to package ratio.** Mean wall watts over mean package watts in each window, and in idle.
- **S5. Depth effect.** Change in tokens per second and in joules per token between depth 64 and each deeper depth, per model.
- **S6. Spread.** Repeat-to-repeat range for every cell. A difference between two cells is called real only if the ranges of their three repeats do not overlap. Nothing is tested with a p-value, and I make no claim from a single cell.
- **S7. Cross-check.** Over each whole round, the plug's own cumulative energy counter against the integral of its polled watts.

## Expectations stated in advance

These are written before the run. One of them, E1, is informed by a single reading: the plug showed 16 W and the package 6 W when the machine was idle on 2026-10-12, before I wrote this plan.

- **E1.** Bare idle wall power is under 25 W. (The ledger on roamingpigs.org says 61 W; I expect that figure was taken under load.)
- **E2.** Decode joules per token (wall, net of idle) are between 1 and 5 for all four models, and lower for the two mixture-of-experts models with about 3 to 4 billion active parameters than for the two dense models.
- **E3.** The wall to package ratio is not a constant: it is above 2 at idle and between 1.2 and 1.6 under load.
- **E4.** Tokens per second fall as depth rises, by 10 to 50% between depth 64 and 32,768, and joules per token rise.
- **E5.** The Q8_0 35B mixture of experts is slower than the 4-bit 26B mixture of experts.
- **E6.** Repeat-to-repeat spread in tokens per second is under 5% in every cell.

I will report which of these were wrong.

## What this study cannot show

- Anything about other hardware, other chips, discrete GPUs, other backends (ROCm is not tested) or other builds of `llama.cpp`.
- Absolute accuracy of the wall watts. The plug is uncalibrated and reports integer watts. Package watts are what the chip reports about itself.
- Anything about batched or concurrent serving. Everything is one stream.
- Anything about quality of output. Prompts are licence texts and generations are not scored.
- Whether a different BIOS memory split, kernel setting or ambient temperature changes the result.

## Claims I will not make

Any multiplier against a datacenter GPU, "verified", "validated", "reproduced" (until someone outside this project has done it) and "preregistered".

## What was done before this plan

- Read-only survey of the machine: kernel, Mesa, llama.cpp builds, model files, hwmon sensors.
- One reading of the plug and of the package power at idle (16 W and 6 W).
- A start-up check that the ROCm build of `llama.cpp` finds no GPU.
- Before the run, pipeline smoke tests (a short decode on each model, to check that the server starts, that the cache is reused and that the logs are written). Their power numbers will not be used.

## Addendum, 2026-10-12, before the measured run (pushed after the plan above)

While testing the harness end to end I looked at one short trace from a smoke test (a 9B model at depth 64, 60 s load step). It showed the wall plug at 18 to 19 W idle and about 137 W under load, the package at 4 to 5 W idle and about 94 W under load, and the plug following the load step within about 1 s. So E1 and E3 are not independent predictions: I had seen those numbers. The smoke tests are not used in the results. I also found, in the journal, the periodic request from another host described under "Guards", and added the scheduling rule for it. No cell of the measured run had been run when this addendum was pushed.
