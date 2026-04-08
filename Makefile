.PHONY: setup format lint typecheck test test-fast ci docker-build

setup:
	uv sync

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

lint:
	uv run ruff check src tests

typecheck:
	uv run mypy src tests

test:
	uv run pytest --cov=src --cov-fail-under=85

test-fast:
	uv run pytest tests/ -m "not slow"

ci: lint typecheck test-fast

docker-build:
	docker build -f docker/Dockerfile.base -t traffic_counter:latest .
