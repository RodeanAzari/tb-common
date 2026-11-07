# tb-common: shared cocotb verification helpers for AXI-Stream FPGA designs

Small, tested Python helpers that every testbench in a family of FPGA projects was
about to rewrite:
- an AXI4-Stream driver, monitor and sink with random backpressure
- an in-order scoreboard that explains its first failure
- seeded randomness that always logs its seed

They are project-agnostic: nothing here knows about any protocol, and nothing imports
from a consuming project.

**Status:** `tb-common-v0.1` released 2026-11-03 ([CHANGELOG](CHANGELOG.md)). These
projects pin it in their `requirements.txt`:
- [fpga-eth-core](https://github.com/RodeanAzari/fpga-eth-core): Ethernet MAC + UDP; 21
  cocotb tests
- [fpga-itch-orderbook](https://github.com/RodeanAzari/fpga-itch-orderbook): the NASDAQ
  ITCH order book, which owns this repo
- the CCSDS satellite telemetry receiver

A SerDes lab and a learned-resilience project are gated on it for their testbenches.

## At a glance

| | |
|---|---|
| **What** | `AxisSource` / `AxisSink` / `AxisMonitor`, `InOrderScoreboard`, `get_rng` |
| **Bus widths** | Any; tkeep-aware byte packing (low lanes first), tested at 1, 4 and 8 lanes |
| **Simulator** | cocotb 2.x; self-tested with Verilator |
| **Size** | 317 lines of Python in `src/tb_common/` |
| **Self-tests** | 25 pytest cases plus cocotb against a skid buffer at `DATA_W` 8 and 64; all pass ([CHANGELOG](CHANGELOG.md)) |
| **Proves it catches bugs** | A build that flips one bit at beat 37 must fail: "mismatch after 13 matched item(s)" |
| **Python** | ≥ 3.11; ruff clean |

## Install (at a release tag only)

Consumers pin a tag, never a branch:

```
pip install "tb-common @ git+https://github.com/RodeanAzari/tb-common.git@tb-common-v0.1"
```

## Modules

| Module | What it gives you |
|---|---|
| `tb_common.axis` | `AxisSource` (driver with random tvalid gaps), `AxisSink` (monitor that also drives random tready), `AxisMonitor` (passive), `AxisBeat`, `bytes_to_beats` / `beats_to_bytes` (tkeep-aware) |
| `tb_common.scoreboard` | `InOrderScoreboard`: strict in-order compare. It is pure Python, so it can be unit-tested and used outside cocotb. |
| `tb_common.rng` | `get_rng(name)`: a `random.Random` whose seed is always logged. `SEED=<n>` replays a run. |

`tb_common` itself imports without cocotb (scoreboard and RNG). Import `tb_common.axis`
explicitly; it needs cocotb.

## Use

```python
from tb_common import InOrderScoreboard, get_rng
from tb_common.axis import AxisSink, AxisSource, beats_to_bytes, bytes_to_beats

rng = get_rng("my_test")                       # logs "my_test: SEED=..."
sb = InOrderScoreboard("my_test")
src = AxisSource(dut, dut.clk, "s_", rng=rng, p_valid=0.7)     # finds s_tdata[_i], ...
AxisSink(dut, dut.clk, "m_", rng=rng, p_ready=0.5,
         callback=lambda frame: sb.observe(beats_to_bytes(frame, 8)))
sb.expect(payload)                             # from your reference model
await src.send(bytes_to_beats(payload, 8))
...
sb.check_done()                                # fails if anything expected never came
```

### AXI-Stream drivers

- **Signal discovery.** Signals are found by prefix with an optional `_i`/`_o` suffix
  (`s_tdata`, `s_tdata_i`, ...). Only `tdata` and `tvalid` are required; `tready`,
  `tlast`, `tkeep` and `tuser` are used when present.
- **`AxisSource`.** Offers each beat with probability `p_valid` per cycle. Once tvalid is
  high it holds, with stable data, until the beat is accepted, as the AXI spec requires.
  `p_valid` can be changed between `send()` calls.
- **`AxisSink`.** Drives tready high with probability `p_ready` per cycle, records beats
  on handshakes, groups them into frames on tlast, and calls `callback(frame)` for each.
  `await sink.wait_frames(n)` blocks until n frames have arrived.
- **Timing.** Drivers act right after the rising edge and judge the handshake from the
  values sampled there.

### Scoreboard failure report

`expect()` queues a reference item and `observe()` checks a DUT item against the oldest
one. On the first mismatch it raises `ScoreboardError` with:
- the last `context` matched items (default 8),
- the expected vs. observed item,
- the next few expectations,
- the output of an optional `state_dump()` callback (e.g. model and DUT state).

`fmt=` controls how items print, and `compare=` replaces `==`. Reordering counts as a
mismatch. An extra item fails at once, and a missing item fails at `check_done()`.

### Pitfall: driving extra DUT inputs from your own coroutines

If a test drives sideband inputs itself (for example, changing a destination address
after a stream's first beat), do it on the **falling** edge. A coroutine woken by the same
rising edge as `AxisSource` can see a handshake one edge early and write on the edge the
DUT samples. fpga-eth-core's `udp_tx` test hit exactly this. It drove the DUT on a
rising edge, and a correct design failed; on falling edges the race cannot happen.

## Verification

`make ci` runs:

| Check | What it proves |
|---|---|
| ruff | Lint and import order on `src/` and `tests/` |
| Verilator `-Wall` | The test DUT (`tests/hdl/axis_reg.sv`, a skid buffer) lints clean |
| pytest, 25 cases | Every scoreboard failure path (mismatch with context and state dump, reordering, extra item, missing item), RNG reproducibility from a seed and seed logging, byte packing round trips at 1, 4 and 8 lanes |
| cocotb, `DATA_W` 8 and 64 | Random tvalid gaps and tready stalls (300 frames) and full throughput (200 frames): every frame intact and in order, monitor beat count equals source beat count |
| cocotb, corrupted build | `CORRUPT_BEAT=37` flips one data bit in the DUT; the scoreboard must fail (an `expect_fail` test) |

### Bugs found

1. **Seeds were invisible under cocotb.** pytest's log capture saw the `SEED=` lines, but
   cocotb runs showed none. cocotb only displays INFO from loggers under `cocotb.*`, and
   the logger was named `tb_common.rng`. The loggers are now named `cocotb.tb_common.*`.
   That changes the name only; the module still doesn't import cocotb.

## Limitations

- **In-order scoreboard only.** No out-of-order or keyed matching yet. A design that
  legitimately reorders needs its own matcher.
- **No functional-coverage helpers yet.** They are planned for a later tag, when the order
  book's coverage-closure phase needs them.
- **tkeep must be contiguous from the low lane** (e.g. `0b0111`). Sparse tkeep raises.
- **Tested with Verilator only.** Other simulators that cocotb supports should work but
  are unverified.

## Build and test

```
python -m venv .venv && .venv/bin/pip install -e . pytest ruff
make ci PY=.venv/bin/python      # lint + pytest + cocotb (needs Verilator on PATH)
```

## Repository layout

| Path | Contents |
|---|---|
| `src/tb_common/` | The package: `axis.py`, `scoreboard.py`, `rng.py` |
| `tests/test_pure.py` | pytest: scoreboard, RNG, byte packing |
| `tests/test_axis_cocotb.py`, `tests/run_cocotb.py` | cocotb self-tests and their Verilator runner |
| `tests/hdl/axis_reg.sv` | Skid-buffer test DUT, with an optional planted corruption |
| `CHANGELOG.md` | Each release with its gate test and evidence |

## Releases

Tags are cut only after the release's gate test passes, and each is recorded in the
CHANGELOG with the command, result and evidence. A change to the interface means a new
tag and a note on what consumers must change.

## Used by

| Project | What it is | Consumes |
|---|---|---|
| [fpga-itch-orderbook](https://github.com/RodeanAzari/fpga-itch-orderbook) (private) | NASDAQ ITCH 5.0 market data to a hardware order book on the Arty A7 | `tb-common-v0.1` |
| [ccsds-meteor-lrpt-receiver](https://github.com/RodeanAzari/ccsds-meteor-lrpt-receiver) (private) | CCSDS satellite telemetry receiver | `tb-common-v0.1` |
| [serdes-lab](https://github.com/RodeanAzari/serdes-lab) (private) | Open SerDes Lab | `tb-common-v0.1` |
| [fpga-eth-core](https://github.com/RodeanAzari/fpga-eth-core) | Payload-agnostic 10/100 Ethernet MAC + IPv4/UDP for 7-series FPGAs | `tb-common-v0.1` |

## License

MIT, see [LICENSE](LICENSE).
