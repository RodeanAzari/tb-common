PY ?= python3

.PHONY: test lint ci

lint:
	$(PY) -m ruff check src tests
	verilator --lint-only -Wall tests/hdl/axis_reg.sv

test:
	PYTHONPATH=src $(PY) -m pytest -q tests/test_pure.py tests/test_coverage.py
	$(PY) tests/run_cocotb.py

ci: lint test
