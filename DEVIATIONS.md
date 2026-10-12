# Deviations from PLAN.md

PLAN.md is not edited after the run started. Everything that differs from it is written here, with the date.

## 2026-10-12: run 1 stopped early, run 2 finished the plan

- Run 1 started about 08:40 UTC. It completed all of round 1 and the first four cells of round 2, then stopped at about 10:42 UTC. In round 2, model gemma4-26b-a4b-q4 at depth 4,096, `llama-server` answered a decode request with HTTP 500 ("The model produced output that does not match the expected Content-only format"). The output it was producing was repeated junk. I first wrote that the server then exited. That was wrong: the "cleaning up before exit" line in its log came from my harness stopping it after the crash. The harness had no handler for that, so it crashed.
- Harness change (commit after this one is written): a failed request is logged as `cell_failed`, the server is restarted, and the cell is repeated once at the end, the same as a contaminated cell. A new option `--cells-file` runs only the listed cells in plan order.
- Run 2 repeats the 30 cells that run 1 did not finish cleanly: the failed cell, the two contaminated cells from round 1 (gemma4-26b-a4b-q4 and qwen35-9b-q4km at depth 16,384), and everything after the crash. The list is `harness/cells-run2.json`.
- So the three rounds of a cell can come from two runs, with a restart of the machine's idle state between them. Run 2 skips the plug load step. It records its own 5 minute bare idle at start and end.
- Cells from run 1 that were clean are kept as they are. Nothing was dropped because of its result.

### Outcome of run 2 (written 2026-10-12, after it finished)

- Run 2 finished 29 cells. One cell never produced a result: gemma4-26b-a4b-q4 at depth 4,096, round 2. The server returned the same HTTP 500 three times (once in run 1, twice in run 2, the second time as the repeat at the end). That cell has 2 repeats instead of 3. The three attempts are in the logs as `cell_failed`.
- Cause: see the next section. It was first written here as "not found"; it was found on 2026-10-12 evening.
- `harness/analyze.py` changed after the run: the plug energy cross-check (S7) now splits the span at sampling gaps longer than 60 s, because the merged data has a gap between run 1 and run 2. The merged data is in `results/merged/` (events, plug and hwmon files joined in time order; the contaminated run 1 cells are replaced by their run 2 repeats).

## 2026-10-12 evening: root cause of the HTTP 500, and the harness fix

- **Cause.** `llama-server` runs every finished reply through a chat parser, including replies to `/completion`. For a model whose template has no special format the parser is a plain "content to the end" rule, and that rule rejects text that is not valid UTF-8. The parse failure becomes an HTTP 500 after the generation has finished and its timings have been logged. This is upstream issue 27543 (`ggml-org/llama.cpp`), fixed by PR 29161, merged 2026-09-20 and first in build b11063. This study runs b10970, which is 93 commits older. I read the b10970 source (`tools/server/server-queue.cpp` creates a parse state for every request, `common/chat.cpp` throws on a failed final parse) and the three failing server logs I still have (Vulkan run 1, the Vulkan repeat in run 2, ROCm run 1): each holds invalid UTF-8 bytes in the rejected text. The first Vulkan failure in run 2 had its log overwritten by the repeat, so I could not check that one.
- **Why it hits some cells.** With greedy decoding and a forced 512 tokens, the 26B mixture-of-experts model sometimes degenerates into repeated junk that includes bytes that are not valid UTF-8. It is deterministic given the same cache state, so the repeat at the end failed too. Other models and depths did not hit it.
- **What I did not do.** I did not upgrade or patch the build, because that would change the software between the Vulkan and ROCm comparison and the results already reported. I did not change the sampling settings.
- **Fix in the harness** (commit after this note): when the reply is an HTTP 500 carrying that parse message, the harness reads the server's own `print_timing` lines for that request from its log, and accepts the request only if the log shows the full 512 generated tokens. The request is then logged with `parse_error: true`, and the decode time and token count come from the server log instead of the reply. Anything else (another error, no timings in the log, a short generation) still fails the cell as before. `tests/test_parse_error.py` covers this with real log lines and a break test, and `analyze.py` reports how many requests were recovered this way.
- **What this changes about the numbers.** The energy and speed of such a request are measured the same way as any other: the generation ran to its 512 tokens on the same hardware, and the power meters did not depend on the reply. The one thing taken from a different place is the decode time (the server log instead of the reply). I check this against the neighbouring requests when the repeats come in.
- **Repeats.** The cells that failed (Vulkan 26B at depth 4,096 round 2, and every ROCm cell that fails the same way) are repeated with the fixed harness after the ROCm run finishes. Those cells will carry `parse_error` requests and say so in the report.

## 2026-10-12 evening: ROCm run stopped, plan 3

- `PLAN-ROCM.md` was pushed (commit 4d5121a, 18:21:18Z) and its run started at about 18:21 UTC. I stopped it at about 19:05 UTC after 3 of 48 cells, one of which had failed with the UTF-8 parse error, and had the harness fix written. Its partial data is kept in `results/rocm1-aborted/`. It has not been analysed and is not used in any result.
- Reason: a ROCm run on a different day from the Vulkan run confounds backend and day, and Vulkan would still be a two-run splice. `PLAN-3.md` replaces it with one paired session after a reboot.
- `PLAN-ROCM.md` is superseded and stays in the repository as a record.
