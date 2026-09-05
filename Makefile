.PHONY: install-deps lint run test

lint:
	uv run ruff check .
	uv run mypy .

test:
	uv run pytest

install-deps:
	uv sync

run:
	uv run journalbot
