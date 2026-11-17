# Changelog

Releases are tagged only after the gate test in `~/fpga-coord/dependencies.toml` passes.

## tb-common-v0.2 (2026-11-17)

**Contents:** adds `tb_common.coverage`: `snapshot`/`export` (a process's cocotb-coverage
points and crosses to JSON), `load`, `merge` (hits summed per bin across processes),
`holes` (bins below `at_least`; exclusions must name a real bin and carry a written
reason), `report_html`. Optional extra `coverage` (cocotb-coverage). Also the MIT license
(`LICENSE`). Nothing existing changed: v0.1 consumers need do nothing.

**Gate test:** "Coverage export/merge/holes/report helper (merges per-process bins, reports
holes, honours written exclusions); self-tests pass; used by P2's `make cov`; no imports
from P2 code".

| Check | Command | Result |
|---|---|---|
| Self-tests | `make ci PY=<venv python>` | ruff clean; Verilator lint clean; pytest 33 passed (8 new for coverage); cocotb skid buffer at DATA_W 8 and 64, 3/3 each |
| Tests catch real bugs | 3 injected into `coverage.py`, one at a time | each fails a test: merge by `max` instead of sum; holes as `hits == 0` instead of `< at_least`; exclusions not checked |
| Used by P2 | OrderBook `make cov` (28 parameter sets) | 14 coverage files merged: 17 items, 178 bins, 0 holes, 0 exclusions (`docs/reports/coverage/` in fpga-itch-orderbook) |
| No P2 imports | `grep -rE "model\|feed\|book\|itch" src/` | none |

## tb-common-v0.1 (2026-11-03)

**Contents:** `tb_common.axis` (AxisSource / AxisSink / AxisMonitor, tkeep-aware byte
packing), `tb_common.scoreboard.InOrderScoreboard` (context dump on first mismatch),
`tb_common.rng.get_rng` (logged, replayable seeds). No imports from any project's code.

**Gate test:** "AXI-Stream driver/monitor + in-order scoreboard (context dump on mismatch) +
seeded random, used by P2's own tests; no imports from P2 code".

| Check | Command | Result |
|---|---|---|
| Self-tests | `make ci PY=<venv python>` | ruff clean; Verilator lint clean; pytest 25 passed; cocotb skid buffer at DATA_W 8 and 64, 3/3 pass each (300 + 200 random frames, random backpressure, 0 mismatches) |
| Catches real bugs | same (`CORRUPT_BEAT=37` build) | expect_fail test fails as required: "mismatch after 13 matched item(s)" |
| Used by P2's own tests | `fpga-eth-core`: `python tb/run.py` | `async_fifo` tests use AxisSource/AxisSink/InOrderScoreboard/get_rng: 3/3 pass at depth 16 and 2048, 3,000 words each, 0 mismatches |
| No P2 imports | `grep -rE "model\|feed\|book\|itch" src/` | none |
