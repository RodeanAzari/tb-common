# tb-common

Project-agnostic cocotb verification helpers, shared by the FPGA projects (P2 order book,
P3 CCSDS receiver, P4 SerDes lab, P5 learned resilience). They know nothing about any
project's protocol.

| Module | What it gives you |
|---|---|
| `tb_common.axis` | `AxisSource` (driver, random tvalid gaps), `AxisSink` (monitor + random tready), `AxisMonitor` (passive), `AxisBeat`, `bytes_to_beats` / `beats_to_bytes` (tkeep-aware) |
| `tb_common.scoreboard` | `InOrderScoreboard`: strict in-order compare. On the first mismatch it raises with the last N matched items, expected vs. observed, the next expectations and an optional state dump. `check_done()` fails on items that were never observed. |
| `tb_common.rng` | `get_rng(name)`: a `random.Random` whose seed is always logged. `SEED=<n>` replays a run. |

## Install (at a release tag only)

```
pip install "tb-common @ git+https://github.com/RodeanAzari/tb-common.git@tb-common-v0.1"
```

## Use

```python
from tb_common import InOrderScoreboard, get_rng
from tb_common.axis import AxisSink, AxisSource, beats_to_bytes, bytes_to_beats

rng = get_rng("my_test")
sb = InOrderScoreboard("my_test")
src = AxisSource(dut, dut.clk, "s_", rng=rng, p_valid=0.7)     # finds s_tdata[_i], ...
AxisSink(dut, dut.clk, "m_", rng=rng, p_ready=0.5,
         callback=lambda frame: sb.observe(beats_to_bytes(frame, 8)))
sb.expect(payload)
await src.send(bytes_to_beats(payload, 8))
...
sb.check_done()
```

Signals are found by prefix with an optional `_i`/`_o` suffix. Only `tdata` and `tvalid`
are required; `tready`, `tlast`, `tkeep` and `tuser` are used when present. Drivers act
right after the rising edge and judge the handshake from the values sampled there.

## Tests

`make ci` runs ruff, Verilator lint, pure-Python tests (every scoreboard failure path,
RNG reproducibility, byte packing at 1/4/8 lanes) and cocotb tests against a skid buffer at
`DATA_W` 8 and 64 with random backpressure. It includes a build with one flipped bit that
the scoreboard must catch (an `expect_fail` test).
