SHELL := $(shell which bash)
UV    := uv
PY    := .venv/bin/python

# ── Dev server ────────────────────────────────────────────────────────────────
run:
	$(UV) run uvicorn app.main:app --port 8008 --reload \
    --reload-dir app \


# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	$(UV) run pytest -v -s --cov=app  --cov-report=term    # full unit + integration suite (fast, ~30s)
test-all:
	$(UV) run pytest -m slow   # also run the full ~11k-line corpus ingestion test


# ── Lint & format ─────────────────────────────────────────────────────────────
format:
	$(UV) run ruff format .
lint:
	$(UV) run ruff check .
	$(UV) run ruff format --diff .

lint-fix:
	$(UV) run ruff format .
	$(UV) run ruff check . --fix

# ── Type check ────────────────────────────────────────────────────────────────
types:
	$(UV) run mypy app

# ── Run everything ────────────────────────────────────────────────────────────
check: lint-fix lint types test

# ── Database migrations ───────────────────────────────────────────────────────

migrate:
	$(UV) run alembic upgrade head

migrate-new:
	$(UV) run alembic revision --autogenerate -m "$(msg)"

# ── Environment ───────────────────────────────────────────────────────────────
venv:
	uv venv .venv --python=python3.12

install:
	$(UV) sync

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	find . -name __pycache__ -exec rm -rf {} +
	find . -name "*.py[co]" -exec rm -rf {} +
	find . -name .pytest_cache -exec rm -rf {} +
	find . -name .mypy_cache  -exec rm -rf {} +
	find . -name .ruff_cache  -exec rm -rf {} +

.PHONY: run test test-all format lint lint-fix types check migrate migrate-new venv install clean
