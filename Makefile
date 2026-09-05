.PHONY: install-deps lint run test coverage coverage-check

BASE_REF ?= HEAD

lint:
	uv run ruff check .
	uv run mypy .

test:
	uv run pytest

coverage:
	uv run coverage erase
	uv run coverage run --source=src -m pytest
	uv run coverage report --fail-under=80
	uv run coverage html
	uv run coverage xml

coverage-check: coverage
	uv run diff-cover coverage.xml --compare-branch="$(BASE_REF)" --fail-under=80

install-deps:
	uv sync

run:
	uv run journalbot
