"""Run the cocotb self-tests with Verilator. Exit status is non-zero on any failure."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from cocotb_tools.runner import get_results, get_runner

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

CONFIGS = [
    ({"DATA_W": 8}, "0"),
    ({"DATA_W": 64}, "0"),
    ({"DATA_W": 32, "CORRUPT_BEAT": 37}, "1"),  # must fail -> reported as expected fail
]


def main() -> int:
    failed = 0
    for params, corrupt in CONFIGS:
        tag = "_".join(f"{k}{v}" for k, v in params.items())
        build = ROOT / "build" / tag
        runner = get_runner("verilator")
        runner.build(sources=[HERE / "hdl" / "axis_reg.sv"], hdl_toplevel="axis_reg",
                     parameters=params, build_dir=build, always=True,
                     build_args=["-Wall", "--assert", "--timing"])
        os.environ.update({"DATA_W": str(params["DATA_W"]), "CORRUPT": corrupt})
        tests = "scoreboard_catches_corruption" if corrupt == "1" else None
        res = runner.test(hdl_toplevel="axis_reg", test_module="test_axis_cocotb",
                          test_dir=HERE, build_dir=build, testcase=tests)
        _, fails = get_results(res)
        failed += fails
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
