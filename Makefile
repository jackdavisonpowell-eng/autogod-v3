PY := python3
.PHONY: test
test:
	$(PY) -m unittest loop.test_stage loop.test_modes hooks.test_guard -v
