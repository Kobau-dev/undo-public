# First Python on the PATH that satisfies requires-python in pyproject.toml (>=3.11); override with `make install PY=...`.
PY ?= $(shell for p in python3.13 python3.12 python3.11 python3.14 python3.15 python3; do \
	command -v $$p >/dev/null 2>&1 && $$p -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null && { echo $$p; break; }; \
done)
VENV ?= .venv
BIN := $(VENV)/bin

.PHONY: venv install install-macos run record demo crm test dry-run replay clean

venv:
	@test -n "$(PY)" || { echo "Undo needs Python 3.11+ and none was found. Install it (brew install python@3.13, or https://www.python.org/downloads/), then run make install again." >&2; exit 1; }
	$(PY) -m venv $(VENV)

install: venv
	$(BIN)/pip install -U pip
	$(BIN)/pip install -e ".[dev]"

install-macos: install
	$(BIN)/pip install -e ".[macos]"

run:
	$(BIN)/python -m undo run

record:
	$(BIN)/python -m undo record

dry-run:
	$(BIN)/python -m undo run --dry-run

replay:
	$(BIN)/python -m undo analyze --replay $(DIR) "$(REQUEST)"

demo:
	$(BIN)/python -m undo demo

crm:
	$(BIN)/pip install -q -e ".[crm]"
	$(BIN)/python -m demo.crm_app --contact marchand --session-timeout 600

test:
	$(BIN)/pytest -q

clean:
	rm -rf $(VENV) .pytest_cache
	find . -name __pycache__ -type d -exec rm -rf {} +
