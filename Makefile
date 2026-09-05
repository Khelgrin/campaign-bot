.PHONY: lint run

lint:
	uv run ruff check .
	uv run mypy .

install-deps:
	uv sync

run:
	uv run journalbot
