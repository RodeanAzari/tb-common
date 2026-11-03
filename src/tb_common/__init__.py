"""Project-agnostic cocotb verification helpers shared across the FPGA projects."""

from tb_common.rng import get_rng
from tb_common.scoreboard import InOrderScoreboard, ScoreboardError

__all__ = ["InOrderScoreboard", "ScoreboardError", "get_rng"]
__version__ = "0.1.0"

# tb_common.axis needs cocotb at import time; import it explicitly:
#   from tb_common.axis import AxisSource, AxisSink, AxisMonitor, AxisBeat
