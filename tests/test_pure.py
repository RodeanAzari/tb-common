"""pytest: scoreboard, byte packing and RNG without a simulator.

Why: a scoreboard that silently passes on a mismatch, a missing item or an extra item
makes every consumer's 'zero mismatches' claim worthless. Each failure path is pinned.
"""

from __future__ import annotations

import pytest

from tb_common import InOrderScoreboard, ScoreboardError, get_rng


def test_in_order_match_counts() -> None:
    sb = InOrderScoreboard("t")
    for i in range(5):
        sb.expect(i)
    for i in range(5):
        sb.observe(i)
    sb.check_done()
    assert sb.matched == 5


def test_mismatch_reports_context_and_state() -> None:
    sb = InOrderScoreboard("t", context=3, state_dump=lambda: "MODEL_STATE")
    for i in range(10):
        sb.expect(i)
    for i in range(6):
        sb.observe(i)
    with pytest.raises(ScoreboardError) as e:
        sb.observe(99)
    msg = str(e.value)
    assert "mismatch after 6" in msg
    assert "[3] 3" in msg and "[5] 5" in msg and "[2] 2" not in msg  # last 3 only
    assert "expected [6]: 6" in msg and "observed [6]: 99" in msg
    assert "then expected: 7, 8, 9" in msg
    assert "MODEL_STATE" in msg


def test_reordering_is_a_mismatch() -> None:
    sb = InOrderScoreboard("t")
    sb.expect("a")
    sb.expect("b")
    with pytest.raises(ScoreboardError):
        sb.observe("b")


def test_extra_item_fails() -> None:
    sb = InOrderScoreboard("t")
    with pytest.raises(ScoreboardError, match="unexpected item"):
        sb.observe(1)


def test_missing_item_fails_at_end() -> None:
    sb = InOrderScoreboard("t")
    sb.expect(1)
    with pytest.raises(ScoreboardError, match="never observed"):
        sb.check_done()


def test_rng_reproducible_from_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEED", "1234")
    a = [get_rng("x").random() for _ in range(1)]
    b = [get_rng("y").random() for _ in range(1)]
    assert a == b


def test_rng_logs_seed(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    with caplog.at_level(logging.INFO):
        get_rng("named", seed=42)
    assert "named: SEED=42" in caplog.text


@pytest.mark.parametrize("lanes", [1, 4, 8])
@pytest.mark.parametrize("length", [1, 3, 8, 9, 64, 1472])
def test_bytes_roundtrip(lanes: int, length: int) -> None:
    pytest.importorskip("cocotb")
    from tb_common.axis import beats_to_bytes, bytes_to_beats

    payload = bytes((i * 37 + 11) & 0xFF for i in range(length))
    beats = bytes_to_beats(payload, lanes)
    assert sum(b.last for b in beats) == 1 and beats[-1].last
    assert beats_to_bytes(beats, lanes) == payload
