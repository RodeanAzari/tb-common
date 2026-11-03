"""In-order scoreboard that dumps context on the first mismatch.

Pure Python: no cocotb dependency, so it can be unit-tested and reused anywhere.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from typing import Any

_log = logging.getLogger("cocotb.tb_common.scoreboard")


class ScoreboardError(AssertionError):
    """Raised on the first mismatch, unexpected item or leftover expectation."""


class InOrderScoreboard:
    """Compares observed items against expected items strictly in order.

    expect() queues a reference item (from a model); observe() checks a DUT item against
    the oldest queued one. On the first mismatch it raises ScoreboardError with:
      - the last `context` matched pairs,
      - the expected vs. observed item,
      - the next few queued expectations,
      - the output of `state_dump()` if given (e.g. model and DUT state).
    """

    def __init__(
        self,
        name: str,
        context: int = 8,
        compare: Callable[[Any, Any], bool] | None = None,
        fmt: Callable[[Any], str] = repr,
        state_dump: Callable[[], str] | None = None,
    ) -> None:
        self.name = name
        self._compare = compare or (lambda a, b: a == b)
        self._fmt = fmt
        self._state_dump = state_dump
        self._pending: deque[Any] = deque()
        self._history: deque[Any] = deque(maxlen=context)
        self.matched = 0

    def expect(self, item: Any) -> None:
        self._pending.append(item)

    @property
    def pending(self) -> int:
        return len(self._pending)

    def observe(self, item: Any) -> None:
        if not self._pending:
            self._fail("unexpected item (nothing expected)", None, item)
        exp = self._pending[0]
        if not self._compare(exp, item):
            self._fail("mismatch", exp, item)
        self._pending.popleft()
        self._history.append(item)
        self.matched += 1

    def check_done(self) -> None:
        """Call at end of test: every expected item must have been observed."""
        if self._pending:
            self._fail(f"{len(self._pending)} expected item(s) never observed",
                       self._pending[0], None)
        _log.info("%s: %d items matched, 0 mismatches", self.name, self.matched)

    def _fail(self, what: str, exp: Any, obs: Any) -> None:
        lines = [f"{self.name}: {what} after {self.matched} matched item(s)"]
        if self._history:
            lines.append(f"  last {len(self._history)} matched:")
            first = self.matched - len(self._history)
            lines += [f"    [{first + i}] {self._fmt(h)}" for i, h in enumerate(self._history)]
        lines.append(f"  expected [{self.matched}]: {'-' if exp is None else self._fmt(exp)}")
        lines.append(f"  observed [{self.matched}]: {'-' if obs is None else self._fmt(obs)}")
        upcoming = list(self._pending)[1:4]
        if upcoming:
            lines.append("  then expected: " + ", ".join(self._fmt(u) for u in upcoming))
        if self._state_dump is not None:
            lines.append("  state:\n" + self._state_dump())
        msg = "\n".join(lines)
        _log.error(msg)
        raise ScoreboardError(msg)
