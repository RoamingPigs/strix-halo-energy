# Results: batch-1 energy per token on one Strix Halo mini PC

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
- Wall net J/token subtracts about 17 W of idle. Package net J/token is lower (for example 1.20 against 1.64 for the 26B model at depth 64). Say which one you mean.
