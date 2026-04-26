.PHONY: help setup build up down logs test lint clean shell health restart

# Default target
help:
	@echo "🚀 OCR Order Service - Makefile Commands"
	@echo "  make setup      - Prepare runtime dirs & .env template"
	@echo "  make build      - Build Docker images (no-cache)"
	@echo "  make up         - Start all services (OCR + Prometheus + Grafana)"
	@echo "  make down       - Stop and remove containers"
	@echo "  make logs       - Follow OCR logs in real-time"
	@echo "  make test       - Run pytest suite"
	@echo "  make lint       - Run ruff + black (code quality)"
	@echo "  make clean      - Remove containers, volumes, images & runtime files"
	@echo "  make shell      - Open interactive bash inside OCR container"
	@echo "  make health     - Check /health & /ready endpoints"
	@echo "  make restart    - Graceful service restart"

setup:
	@if [ ! -f .env ]; then cp .env.example .env && echo "✅ .env created"; else echo "ℹ️ .env already exists"; fi
	@mkdir -p data input logs output/ordens output/processadas output/revisao output/pending_signature

build:
	docker compose build --no-cache

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f automacao-os

test:
	docker compose run --rm automacao-os python -m pytest tests/ -v --tb=short --ignore=tests/load_test.py

lint:
	docker compose run --rm automacao-os ruff check src/ tests/ scripts/
	docker compose run --rm automacao-os black --check src/ tests/ scripts/

clean:
	docker compose down --volumes --rmi all
	rm -rf data/*.db logs/*.log output/ordens/* output/processadas/* output/revisao/* output/pending_signature/*
	@echo "🧹 Cleanup complete. Runtime state removed."

shell:
	docker compose exec automacao-os /bin/bash

health:
	@echo "🔍 Checking liveness..."
	curl -sf http://localhost:8000/health >/dev/null && echo " ✅ /health OK" || echo " ❌ /health FAILED"
	@echo "🔍 Checking readiness..."
	curl -sf http://localhost:8000/ready >/dev/null && echo " ✅ /ready OK" || echo " ❌ /ready FAILED"

restart:
	docker compose restart automacao-os
	@echo "🔄 Service restarted. Run 'make logs' to monitor."