# =============================================================================
# OmniDrop AI — Makefile
# Usage: make <target>
# =============================================================================

.PHONY: install dev lint test migrate build clean help

BASE_DIR := $(shell pwd)

## install: Install all dependencies (Python + Node + Supabase CLI)
install:
	@echo "→ Installing shared Python package..."
	pip install -e ./shared
	@echo "→ Installing backend dependencies..."
	pip install -r backend/requirements.txt -r backend/requirements-dev.txt
	@echo "→ Installing worker dependencies..."
	pip install -r workers/requirements.txt -r workers/requirements-dev.txt
	@echo "→ Installing data pipeline dependencies..."
	pip install -r data_pipelines/requirements.txt
	@echo "→ Installing frontend dependencies..."
	cd frontend && npm install
	@echo "→ Done. Run 'make dev' to start the development environment."

## dev: Start local development environment
dev:
	@echo "→ Starting Temporal dev server..."
	docker compose up -d temporal
	@echo "→ Starting backend (port 8000)..."
	cd backend && uvicorn api.main:app --reload --port 8000 &
	@echo "→ Starting Temporal workers..."
	cd workers && python worker.py &
	@echo "→ Starting frontend (port 3000)..."
	cd frontend && npm run dev
	@echo ""
	@echo "  Temporal UI:  http://localhost:8233"
	@echo "  Backend docs: http://localhost:8000/docs"
	@echo "  Frontend:     http://localhost:3000"

## lint: Run all linters (ruff, mypy, eslint, tsc)
lint:
	@echo "→ Linting shared..."
	cd shared && ruff check . && mypy .
	@echo "→ Linting backend..."
	cd backend && ruff check . && mypy .
	@echo "→ Linting workers..."
	cd workers && ruff check . && mypy .
	@echo "→ Linting frontend..."
	cd frontend && npx eslint . && npx tsc --noEmit
	@echo "✓ All lint checks passed."

## test: Run all test suites
test:
	@echo "→ Testing backend..."
	cd backend && pytest -v
	@echo "→ Testing workers..."
	cd workers && pytest -v
	@echo "→ Testing frontend..."
	cd frontend && npx vitest run
	@echo "✓ All tests passed."

## migrate: Apply Supabase database migrations
migrate:
	supabase db push

## build: Build all Docker images
build:
	docker compose build

## clean: Stop containers and remove build artifacts
clean:
	docker compose down
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true

## help: Show this help message
help:
	@grep -E '^## ' Makefile | sed 's/## /  /'
