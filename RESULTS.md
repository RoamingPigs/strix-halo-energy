# Results: speed and energy per token on one Strix Halo mini PC

Self-published, not peer reviewed. Plans: `PLAN.md` (study 1, Vulkan), `PLAN-ROCM.md` (superseded), `PLAN-3.md` (the paired run below). What changed after the plans: `DEVIATIONS.md`. Report with charts: `report/report.html` and `report/report.pdf`. Raw logs and tables: `results/`.

## Paired run: Vulkan against ROCm (run `paired4`, 2026-10-12 to 2026-10-13)

One session, both backends, 96 cells (4 models, 4 context depths, 3 repeats, each on Vulkan and on ROCm 7.1 from the Ubuntu archive), on kernel 7.0.0-38, with the machine kept quiet. The last start had no failed cell and no contaminated cell. Three earlier starts were stopped after 3 to 13 cells each because of outside load on the machine (`DEVIATIONS.md` says what, and what was fixed). Their data is kept in `results/*-aborted/` and is not used.

- **Speed.** ROCm decoded more slowly than Vulkan in all 16 model and context combinations, by 1 to 12%. The repeat ranges of the two backends do not overlap in any of them.
- **Energy per token** (wall plug, net of idle). ROCm used 8 to 20% more on the 9B dense model, 6 to 8% less on the 35B mixture, and about the same on the 12B dense model (-6 to +3%) and the 26B mixture (-6 to -1%, repeat ranges overlapping in some cells).
- **Repeatability.** Vulkan on the newer kernel, on another day, matched study 1 within 1.52% in every one of the 16 combinations.
- **Idle.** 17 W at the wall on both backends, against 16.5 W in study 1.
- **Plans against results.** Of my eight expectations for this run, seven held. P5 was wrong: ROCm's wall power under load was 87 to 117% of Vulkan's, not within 15%. It drew 15 to 17% more on the 9B model at 64 and 4k context, and 13% less on the 35B mixture at 64. The six expectations of study 1 (E1 to E6) also held on both backends.
- **The server error.** `llama-server` b10970 answered HTTP 500 on 12 requests, all with the 26B mixture, after a reply with bytes that are not valid UTF-8. The harness took their timings from the server's log; the report counts them.

What this does not show: other ROCm versions or packaging, other kernels than 34 and 38, other chips, output quality, or batched serving. It is one machine and one `llama.cpp` build. The wall plug is uncalibrated and reads whole watts (its energy counter and the sum of its readings differ by 1.7%). Nobody outside this project has repeated it.

# Study 1: Vulkan only (kernel 34)

Self-published, not peer reviewed. Plan: `PLAN.md` (commits 1cbe736 and d078b4e, pushed before the run). What changed after: `DEVIATIONS.md`. Full tables: `results/merged/REPORT.md`. Raw logs: `results/run1/`, `results/run2/`.

## What was measured

47 of 48 planned cells: 4 models, 4 context depths, 3 repeats. One cell (the 26B mixture of experts at depth 4,096) has 2 repeats, because the server failed on the third. No cell was dropped for its result. Wall power is from an uncalibrated smart plug (integer watts). The plug's own energy counter and the integral of its readings agree within 2.2% over the whole study (355.7 Wh against 348.0 Wh), but both come from the same plug, so that checks sampling, not accuracy.

## Numbers (wall power, net of idle; mean over repeats)

| Model | Depth 64 | Depth 32,768 |
|---|---|---|
| 9B dense, Q4 | 37.9 tok/s, 3.31 J/token | 31.6 tok/s, 4.07 J/token |
| 12B dense, Q4 | 29.3 tok/s, 4.51 J/token | 25.7 tok/s, 4.83 J/token |
| 26B mixture of experts (4B active), Q4 | 71.9 tok/s, 1.64 J/token | 53.0 tok/s, 2.26 J/token |
| 35B mixture of experts (3B active), Q8 | 54.1 tok/s, 2.28 J/token | 44.9 tok/s, 2.74 J/token |

Idle: the wall plug reads 16 to 18 W and the chip's package sensor 4 to 5 W. Under load the wall reading is 1.45 to 1.52 times the package reading.

## The six expectations written in advance

All six held: E1 idle under 25 W (16 to 16.5 W), E2 energy between 1 and 5 J/token with the mixture of experts lower (1.64 to 4.83; 2.19 against 4.17 on average), E3 wall to package ratio (about 4 at idle, 1.45 to 1.52 under load), E4 speed falls 12 to 26% from depth 64 to 32,768 with energy rising 7 to 38%, E5 the Q8 model is slower than the Q4 mixture of experts (54.1 against 71.9 tok/s), E6 repeat spread under 1% in every cell.

E1 and E3 were not independent predictions: the addendum to the plan says I had seen smoke test traces. None of my expectations was wrong, which means they were probably too safe, not that the plan was good.

## What this does not show

Nothing about any other hardware, ROCm (not installed), batched serving, output quality or a different room temperature. The wall watts are as accurate as an uncalibrated plug. One machine, one build (llama.cpp b10970, Vulkan). Nobody outside this project has repeated it.

## Things to know before quoting a number

- The 9B model at depth 16,384 draws about 9 W more than at depth 4,096 (149.6 against 140.6 W) while its speed falls only 6%. I have no explanation. It repeated across all three rounds.
- The 26B model at depth 4,096 failed three times with a server error on junk output, so that cell has 2 repeats. Cause unknown.
- During study 1 two things ran on the machine that I found only afterwards (`DEVIATIONS.md`): a five-minute `git` backup load, which the guard flagged in two cells that were repeated, and a crash-looping service that restarted every 10 seconds. Neither is in the paired run.
- Wall net J/token subtracts about 17 W of idle. Package net J/token is lower (for example 1.20 against 1.64 for the 26B model at depth 64). Say which one you mean.
