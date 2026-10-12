# Deviations from PLAN.md

PLAN.md is not edited after the run started. Everything that differs from it is written here, with the date.

## 2026-10-12: run 1 stopped early, run 2 finished the plan

- Run 1 started about 08:40 UTC. It completed all of round 1 and the first four cells of round 2, then stopped at about 10:42 UTC. In round 2, model gemma4-26b-a4b-q4 at depth 4,096, `llama-server` answered a decode request with HTTP 500 ("The model produced output that does not match the expected Content-only format") and exited. The output it was producing was repeated junk. The harness had no handler for that, so it crashed.
- Harness change (commit after this one is written): a failed request is logged as `cell_failed`, the server is restarted, and the cell is repeated once at the end, the same as a contaminated cell. A new option `--cells-file` runs only the listed cells in plan order.
- Run 2 repeats the 30 cells that run 1 did not finish cleanly: the failed cell, the two contaminated cells from round 1 (gemma4-26b-a4b-q4 and qwen35-9b-q4km at depth 16,384), and everything after the crash. The list is `harness/cells-run2.json`.
- So the three rounds of a cell can come from two runs, with a restart of the machine's idle state between them. Run 2 skips the plug load step. It records its own 5 minute bare idle at start and end.
- Cells from run 1 that were clean are kept as they are. Nothing was dropped because of its result.
