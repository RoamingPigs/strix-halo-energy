# Deviations from PLAN.md

PLAN.md is not edited after the run started. Everything that differs from it is written here, with the date.

## 2026-10-12: run 1 stopped early, run 2 finished the plan

- Run 1 started about 08:40 UTC. It completed all of round 1 and the first four cells of round 2, then stopped at about 10:42 UTC. In round 2, model gemma4-26b-a4b-q4 at depth 4,096, `llama-server` answered a decode request with HTTP 500 ("The model produced output that does not match the expected Content-only format") and exited. The output it was producing was repeated junk. The harness had no handler for that, so it crashed.
- Harness change (commit after this one is written): a failed request is logged as `cell_failed`, the server is restarted, and the cell is repeated once at the end, the same as a contaminated cell. A new option `--cells-file` runs only the listed cells in plan order.
- Run 2 repeats the 30 cells that run 1 did not finish cleanly: the failed cell, the two contaminated cells from round 1 (gemma4-26b-a4b-q4 and qwen35-9b-q4km at depth 16,384), and everything after the crash. The list is `harness/cells-run2.json`.
- So the three rounds of a cell can come from two runs, with a restart of the machine's idle state between them. Run 2 skips the plug load step. It records its own 5 minute bare idle at start and end.
- Cells from run 1 that were clean are kept as they are. Nothing was dropped because of its result.

### Outcome of run 2 (written 2026-10-12, after it finished)

- Run 2 finished 29 cells. One cell never produced a result: gemma4-26b-a4b-q4 at depth 4,096, round 2. The server returned the same HTTP 500 three times (once in run 1, twice in run 2, the second time as the repeat at the end). That cell has 2 repeats instead of 3. The three attempts are in the logs as `cell_failed`.
- Cause not found. The server log shows the model repeating junk tokens until the chat-format check rejected it. I did not investigate further, and I do not know whether the cause is the model, the build or the prompt cache.
- `harness/analyze.py` changed after the run: the plug energy cross-check (S7) now splits the span at sampling gaps longer than 60 s, because the merged data has a gap between run 1 and run 2. The merged data is in `results/merged/` (events, plug and hwmon files joined in time order; the contaminated run 1 cells are replaced by their run 2 repeats).
