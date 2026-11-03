"""Seeded randomness that always logs its seed, so every failure reproduces.

Set SEED=<n> in the environment to replay a run.
"""

from __future__ import annotations

import logging
import os
import random

_log = logging.getLogger("cocotb.tb_common.rng")


def get_rng(name: str, seed: int | None = None) -> random.Random:
    """Return a Random for `name`, seeded from `seed`, else $SEED, else fresh entropy.

    The seed is logged as `<name>: SEED=<n>` before any value is drawn.
    """
    if seed is None:
        env = os.environ.get("SEED")
        seed = int(env) if env else random.SystemRandom().randrange(1 << 32)
    _log.info("%s: SEED=%d (rerun with SEED=%d)", name, seed, seed)
    return random.Random(seed)
