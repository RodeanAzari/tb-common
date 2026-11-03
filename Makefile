PY ?= python3

.PHONY: test lint ci

lint:
	$(PY) -m ruff check src tests
	verilator --lint-only -Wall tests/hdl/axis_reg.sv

test:
	$(PY) -m pytest -q tests/test_pure.py
	$(PY) tests/run_cocotb.py

ci: lint test
