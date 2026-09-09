PY := python3
.PHONY: test
test:
	$(PY) -m unittest loop.test_stage hooks.test_guard -v
