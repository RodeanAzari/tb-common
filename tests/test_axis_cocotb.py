"""cocotb tests: tb_common's AXI-Stream source/sink + scoreboard against a skid buffer.

Why: every consumer trusts these drivers to apply real backpressure and to report every
beat exactly once. These tests prove that with random tvalid gaps and tready stalls, at
two bus widths, and prove the scoreboard fails on a one-bit datapath corruption.
"""

from __future__ import annotations

import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from tb_common import InOrderScoreboard, get_rng
from tb_common.axis import AxisSink, AxisSource, beats_to_bytes, bytes_to_beats

DATA_W = int(os.environ.get("DATA_W", "32"))
LANES = DATA_W // 8


async def _setup(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst.value = 1
    await ClockCycles(dut.clk, 3)
    dut.rst.value = 0


async def _stream(dut, name: str, n_frames: int, p_valid: float, p_ready: float) -> None:
    rng = get_rng(name)
    await _setup(dut)
    sb = InOrderScoreboard(name)
    src = AxisSource(dut, dut.clk, "s_", rng=rng, p_valid=p_valid)
    sink = AxisSink(dut, dut.clk, "m_", rng=rng, p_ready=p_ready,
                    callback=lambda f: sb.observe((beats_to_bytes(f, LANES), f[-1].user)))
    for _ in range(n_frames):
        payload = bytes(rng.randrange(256) for _ in range(rng.randint(1, 4 * LANES + 3)))
        user = rng.randrange(16)
        sb.expect((payload, user))
        await src.send(bytes_to_beats(payload, LANES, user=user))
    await sink.wait_frames(n_frames)
    await ClockCycles(dut.clk, 20)
    sb.check_done()
    assert sink.beats_seen == src.beats_sent, "monitor saw a different number of beats"


@cocotb.test()
async def random_backpressure(dut):
    """Random gaps and stalls on both sides: every frame arrives intact and in order."""
    await _stream(dut, "random_backpressure", 300, p_valid=0.6, p_ready=0.5)


@cocotb.test()
async def full_throughput(dut):
    """No gaps, no stalls: one beat per cycle end to end."""
    await _stream(dut, "full_throughput", 200, p_valid=1.0, p_ready=1.0)


@cocotb.test(expect_fail=os.environ.get("CORRUPT", "0") == "1")
async def scoreboard_catches_corruption(dut):
    """Built with CORRUPT_BEAT set, this run must FAIL (expect_fail): proof that the
    monitor + scoreboard detect a single flipped bit in a real DUT."""
    await _stream(dut, "corruption", 50, p_valid=0.8, p_ready=0.7)
