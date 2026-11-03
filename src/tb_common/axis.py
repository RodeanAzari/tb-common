"""AXI4-Stream driver (source), passive monitor, and sink (monitor + tready driver).

Signals are found by prefix: for prefix "s_" the source looks for s_tdata, s_tvalid,
s_tready, s_tlast, s_tkeep, s_tuser, each with an optional _i/_o suffix. Only tdata and
tvalid are required.

Timing convention: everything acts right after a rising clock edge. The handshake of
the cycle that just ended is judged from the values sampled there, then the next
cycle's inputs are written.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import cocotb
from cocotb.triggers import Event, RisingEdge


@dataclass(frozen=True)
class AxisBeat:
    data: int
    last: bool = False
    keep: int | None = None
    user: int | None = None


Frame = list[AxisBeat]


def bytes_to_beats(payload: bytes, byte_lanes: int, user: int | None = None) -> Frame:
    """Pack bytes little-endian into beats (byte 0 in tdata[7:0]); tkeep marks valid
    lanes; tlast on the final beat. Empty payloads are not representable in AXI-Stream."""
    if not payload:
        raise ValueError("AXI-Stream cannot carry an empty frame")
    beats = []
    for off in range(0, len(payload), byte_lanes):
        chunk = payload[off:off + byte_lanes]
        beats.append(AxisBeat(
            data=int.from_bytes(chunk, "little"),
            keep=(1 << len(chunk)) - 1,
            last=off + byte_lanes >= len(payload),
            user=user,
        ))
    return beats


def beats_to_bytes(frame: Sequence[AxisBeat], byte_lanes: int) -> bytes:
    """Inverse of bytes_to_beats. A beat with keep=None counts as all lanes valid.
    Only contiguous low-lane keep patterns (e.g. 0b0111) are accepted."""
    out = bytearray()
    full = (1 << byte_lanes) - 1
    for b in frame:
        keep = full if b.keep is None else b.keep
        n = keep.bit_length()
        if keep != (1 << n) - 1:
            raise ValueError(f"non-contiguous tkeep {keep:#x}")
        out += b.data.to_bytes(byte_lanes, "little")[:n]
    return bytes(out)


def _find(dut: Any, prefix: str, name: str, required: bool) -> Any:
    for cand in (f"{prefix}{name}", f"{prefix}{name}_i", f"{prefix}{name}_o"):
        if hasattr(dut, cand):
            return getattr(dut, cand)
    if required:
        raise AttributeError(f"{dut._name}: no signal {prefix}{name}[_i|_o]")
    return None


class _Bus:
    def __init__(self, dut: Any, prefix: str) -> None:
        self.tdata = _find(dut, prefix, "tdata", True)
        self.tvalid = _find(dut, prefix, "tvalid", True)
        self.tready = _find(dut, prefix, "tready", False)
        self.tlast = _find(dut, prefix, "tlast", False)
        self.tkeep = _find(dut, prefix, "tkeep", False)
        self.tuser = _find(dut, prefix, "tuser", False)

    def handshake(self) -> bool:
        return self.tvalid.value == 1 and (self.tready is None or self.tready.value == 1)

    def sample(self) -> AxisBeat:
        return AxisBeat(
            data=int(self.tdata.value),
            last=True if self.tlast is None else bool(self.tlast.value),
            keep=None if self.tkeep is None else int(self.tkeep.value),
            user=None if self.tuser is None else int(self.tuser.value),
        )


class AxisSource:
    """Drives beats into a DUT's AXI-Stream sink port.

    `p_valid` is the chance tvalid is offered on a cycle when a beat is waiting (random
    gaps). Once tvalid is high it holds, with stable data, until accepted, per the spec.
    """

    def __init__(self, dut: Any, clk: Any, prefix: str, rng: random.Random | None = None,
                 p_valid: float = 1.0) -> None:
        self.bus = _Bus(dut, prefix)
        self.clk = clk
        self.rng = rng or random.Random(0)
        self.p_valid = p_valid
        self.bus.tvalid.value = 0
        self.beats_sent = 0

    async def send(self, beats: Iterable[AxisBeat]) -> None:
        bus = self.bus
        pending = list(beats)
        i = 0
        holding = False  # tvalid was high and not yet accepted: must keep offering
        while i < len(pending):
            if holding or self.rng.random() < self.p_valid:
                b = pending[i]
                bus.tdata.value = b.data
                if bus.tlast is not None:
                    bus.tlast.value = int(b.last)
                if bus.tkeep is not None and b.keep is not None:
                    bus.tkeep.value = b.keep
                if bus.tuser is not None and b.user is not None:
                    bus.tuser.value = b.user
                bus.tvalid.value = 1
            else:
                bus.tvalid.value = 0
            await RisingEdge(self.clk)
            holding = bus.tvalid.value == 1
            if bus.handshake():
                i += 1
                self.beats_sent += 1
                holding = False
        bus.tvalid.value = 0

    async def send_frame(self, words: Sequence[int]) -> None:
        """Convenience: one beat per word, tlast on the last."""
        await self.send(AxisBeat(w, last=(k == len(words) - 1)) for k, w in enumerate(words))


class AxisMonitor:
    """Passively records beats on handshakes and groups them into frames on tlast.

    `callback(frame)` is called for every completed frame. Without tlast on the bus,
    every beat is a one-beat frame.
    """

    def __init__(self, dut: Any, clk: Any, prefix: str,
                 callback: Callable[[Frame], None] | None = None) -> None:
        self.bus = _Bus(dut, prefix)
        self.clk = clk
        self.callback = callback
        self.frames: list[Frame] = []
        self.beats_seen = 0
        self._partial: Frame = []
        self._new_frame = Event()
        cocotb.start_soon(self._run())

    async def _run(self) -> None:
        while True:
            await RisingEdge(self.clk)
            if self.bus.handshake():
                beat = self.bus.sample()
                self.beats_seen += 1
                self._partial.append(beat)
                if beat.last:
                    frame, self._partial = self._partial, []
                    self.frames.append(frame)
                    if self.callback is not None:
                        self.callback(frame)
                    self._new_frame.set()

    async def wait_frames(self, n: int) -> None:
        while len(self.frames) < n:
            self._new_frame.clear()
            await self._new_frame.wait()


class AxisSink(AxisMonitor):
    """A monitor that also drives tready, high with probability `p_ready` per cycle."""

    def __init__(self, dut: Any, clk: Any, prefix: str, rng: random.Random | None = None,
                 p_ready: float = 1.0,
                 callback: Callable[[Frame], None] | None = None) -> None:
        super().__init__(dut, clk, prefix, callback)
        if self.bus.tready is None:
            raise AttributeError(f"{prefix}tready not found; use AxisMonitor instead")
        self.rng = rng or random.Random(0)
        self.p_ready = p_ready
        self.bus.tready.value = 0
        cocotb.start_soon(self._drive_ready())

    async def _drive_ready(self) -> None:
        while True:
            self.bus.tready.value = int(self.rng.random() < self.p_ready)
            await RisingEdge(self.clk)
