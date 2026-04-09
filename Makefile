.PHONY: setup format lint typecheck test ci

setup:
	uv sync

lint:
	uv run ruff format . --exclude test*
	uv run ruff check --fix . --exclude test*

typecheck:
	uv run mypy . --exclude test*

test:
	uv run pytest --cov=src --cov-fail-under=85

ci: lint typecheck test
