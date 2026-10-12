# Analysis plan 3: Vulkan and ROCm in one paired session, on the newer kernel

Author: Cisco Caceres. Self-published, not peer reviewed. Written 2026-10-12, before the paired run. `PLAN.md` and `PLAN-ROCM.md` are not edited. Everything not stated here is as in `PLAN.md`. This file is pushed before the run starts, and the push time is on GitHub.

## Why a third plan

- Study 1 (`PLAN.md`) measured Vulkan on kernel 7.0.0-34. Its results are spliced from two runs, because the first stopped when `llama-server` answered HTTP 500, and one cell has 2 repeats instead of 3.
- `PLAN-ROCM.md` set out to measure ROCm the same way, on another day. I stopped that run after 3 of its 48 cells, because a ROCm and a Vulkan run on different days confound the backend with the day (room temperature, machine state), and because the harness would have recorded a second failure of the same kind. Its partial logs are in `results/rocm1-aborted/`. I have not analysed them and will not until this paired run is reported. They are not used in any result.
- The 500 was found: `llama-server` b10970 rejects, at the end of a finished reply, any text that is not valid UTF-8 (upstream issue 27543, fixed in b11063). The harness now recovers the request's timings from the server's own log when that happens. `DEVIATIONS.md` has the whole account. `tests/test_parse_error.py` covers it.

## What this plan does

One session, both backends, 96 cells: 4 models, 4 context depths, 3 rounds, on each of Vulkan (`b10970-vulkan`) and ROCm (`b10970-rocm`, HIP runtime 7.1.0 from the Ubuntu 26.04 archive). In each round every model runs on both backends back to back. The order of models, the order of the two backends within a model and the order of depths within each block are seeded shuffles (seed 20261014, `harness/plan-paired.json`). So slow drift in the room or the machine falls on both backends alike. Repeat count, window, settles, idle blocks, guards, meters, flags, prompts and models are as in `PLAN.md`. The plug lag step runs once, at the start, on the Vulkan build.

The machine is rebooted first, onto the already installed kernel 7.0.0-38-generic. `harness/preflight.py` checks the kernel, the command line (`amd_iommu=off ttm.pages_limit=31457280 amdgpu.gttsize=131072 amdgpu.cwsr_enable=0`), the governor, that both builds see the GPU, that the machine is quiet, the plug, the clock offset and that this plan is on GitHub, and the run does not start unless it passes.

A cell whose request meets the UTF-8 parse error is accepted if the server log shows all 512 tokens, and it is flagged `parse_error` in the data and the report. A cell that is contaminated or fails for any other reason is repeated once at the end, as before.

## Disclosed before the run

- I have seen the Vulkan results of study 1 (`RESULTS.md`) and one ROCm smoke test (26B mixture of experts, short prompt, 66.5 to 68.0 tokens per second). I saw the ROCm run's progress only as cell counts and one failed cell. So the expectations below are not independent predictions, and several are weak on purpose.
- In a harness check on 2026-10-12, with a 20 s window, the 26B model at depth 16,384 on ROCm decoded about 54 to 55 tokens per second and on Vulkan about 58 to 59. That is also not used in any result. It shows the ROCm parse error recurring on that cell and the cache being reused after it.
- The reboot also changes the kernel from 34 to 38. The comparison of today's Vulkan with study 1's Vulkan therefore mixes a kernel change and a day change. I will not attribute a difference to either one.

## Expectations stated in advance

- **P1.** Vulkan on kernel 38 is within 3% of study 1's Vulkan tokens per second in every cell.
- **P2.** ROCm decode speed is within 25% of Vulkan in every cell, and below Vulkan for the 26B mixture of experts at depth 64.
- **P3.** For at least one model the ROCm minus Vulkan gap shrinks or reverses between depth 64 and depth 32,768.
- **P4.** Idle wall power is under 25 W, and within 2 W of study 1's idle median (16 to 18 W), in both backends.
- **P5.** Wall power under load is within 15% between the backends for the same cell.
- **P6.** The models rank the same way by wall net joules per token in both backends.
- **P7.** Repeat spread in tokens per second is under 5% in every cell of both backends.
- **P8.** After the harness fix all 96 cells complete with 3 repeats, and the parse error appears only with the 26B mixture-of-experts model.

I will report which were wrong.

## Pre-specified analyses

`analyze.py` is run once per backend on the events of that backend (S1 to S7 of `PLAN.md`). `compare.py` then gives, cell by cell, ROCm over Vulkan for tokens per second, wall watts, package watts and wall net joules per token, with the repeat ranges. A difference is called real only if the min to max ranges of the repeats do not overlap. Nothing is tested with a p-value. The comparison of the two Vulkan sessions (study 1 and this one) is reported the same way, with the caveat above.

## What this does not show

Anything about other ROCm versions or packaging, other kernels than 34 and 38, other chips, quality of output, batched serving, or a different room temperature. The wall meter caveats of `PLAN.md` apply unchanged. Whether the recovered timings differ from reply timings is checked only by comparing recovered requests with their neighbours in the same cell.

## Claims I will not make

Any multiplier against a datacenter GPU, "verified", "validated", "reproduced" and "preregistered". "Faster" or "slower" only where the repeat ranges do not overlap.
