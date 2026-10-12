# Analysis plan 2: the same study on the ROCm build

Author: Cisco Caceres. Self-published, not peer reviewed. Written 2026-10-12, before the ROCm run. `PLAN.md` is the first plan and is not edited; everything not stated here is as in `PLAN.md`. This file is pushed before the run starts.

## What changes

| Item | PLAN.md (done) | This plan |
|---|---|---|
| Backend | `llama.cpp` b10970, Vulkan (Mesa RADV) | the same release, ROCm build `b10970-rocm`, HIP runtime 7.1.0 from the Ubuntu 26.04 archive (libamdhip64-7, librocblas5, libhipblas3) |
| Order | seed 20261012 | seed 20261013 (`harness/plan-rocm.json`) |
| Everything else | | the same four model files (SHA-256 recorded again), flags, depths, window, settles, idle blocks, repeat count, plug lag step, contamination guards, power meters |

The running kernel is still 7.0.0-34-generic, as in the first run. A newer kernel (7.0.0-38) is installed on the machine and not booted, so the two runs share a kernel. The ROCm packages are installed system-wide, so Mesa and the kernel driver are unchanged.

## Disclosed before the run

- I ran one ROCm smoke test on 2026-10-12, after installing the runtime: the 26B mixture of experts at a few tokens of prompt decoded at 66.5 to 68.0 tokens per second. That is about 6 to 8% below the Vulkan figure in the first study at depth 64 (71.9). It is not used in results. The expectations below were written after seeing it, so R1 is not an independent prediction for that model.
- Nothing else about ROCm was measured before this plan.

## Expectations stated in advance

- **R1.** ROCm decode speed is within 25% of Vulkan in every cell, and below Vulkan for the 26B mixture of experts at depth 64 (seen in the smoke test).
- **R2.** For at least one model, the ROCm minus Vulkan speed gap shrinks or reverses between depth 64 and depth 32,768 (I guess ROCm's attention kernels hold up better at long context; I have no measurement).
- **R3.** Idle wall power with the ROCm runtime installed is still under 25 W, and within 2 W of the first run's idle median (16 to 18 W).
- **R4.** Wall power under load is within 15% of Vulkan for the same cell.
- **R5.** Wall net joules per token rank the models the same way as under Vulkan (26B mixture, then 35B mixture, then 9B dense, then 12B dense at depth 64).
- **R6.** Repeat spread in tokens per second is under 5% in every cell.

I will report which were wrong. If a model does not load, or a cell fails, that goes in a `DEVIATIONS-ROCM.md` and in the report. Failures are not dropped.

## Pre-specified comparison

For each model and depth, ROCm over Vulkan: tokens per second, wall watts, package watts, wall net joules per token, with the repeat ranges of both runs. A difference is called real only if the ranges of the repeats do not overlap (as in `PLAN.md`, S6). The Vulkan figures are the merged results of the first study (`results/merged/`). The comparison is between two runs on different days of the same machine; ambient temperature is not controlled.

## What this does not show

Anything about other ROCm versions, the vendor's own ROCm packages, other kernels, other chips, quality of output, or batched serving. Whether a different `llama.cpp` build flag (for example rocWMMA) changes the result is not tested. The power meter caveats from `PLAN.md` apply unchanged.

## Claims I will not make

Any multiplier against a datacenter GPU, "verified", "validated", "reproduced" and "preregistered". "Faster" or "slower" only where the repeat ranges do not overlap.
