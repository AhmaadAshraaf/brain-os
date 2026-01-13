.PHONY: up-online up-offline up-local ingest-dev clean sync-down test-api test-ingest help

# Default target
help:
	@echo "Brain-OS v3.0 - Available Commands"
	@echo "=================================="
	@echo "  up-online    Start production stack (VM with ingest service)"
	@echo "  up-offline   Start offline stack (Laptop, read-only Qdrant)"
	@echo "  up-local     Alias for up-offline"
	@echo "  ingest-dev   Run ingest service in development mode"
	@echo "  sync-down    Pull latest Qdrant snapshot from Wasabi S3"
	@echo "  test-api     Run pytest on API service"
	@echo "  test-ingest  Run pytest on ingest service (Docker)"
	@echo "  clean        Stop all containers and remove volumes"

# Production stack (VM) - includes ingest service
up-online:
	docker compose -f infra/docker-compose.base.yml -f infra/docker-compose.prod.yml up -d

# Offline stack (Laptop) - read-only Qdrant, no ingest
up-offline:
	docker compose -f infra/docker-compose.base.yml -f infra/docker-compose.local.yml up -d

# Alias for offline
up-local: up-offline

# Development mode for ingest service
ingest-dev:
	cd ingest && python -m src.main

# Pull latest snapshot from Wasabi S3
sync-down:
	./scripts/snapshot_pull.sh

# Run API tests
test-api:
	cd api && pytest -v

# Run ingest tests in Docker (requires services to be running via make up-online)
test-ingest:
	docker-compose exec ingest pytest tests/ -v

# Cleanup
clean:
	docker compose -f infra/docker-compose.base.yml -f infra/docker-compose.prod.yml down -v --remove-orphans
	docker compose -f infra/docker-compose.base.yml -f infra/docker-compose.local.yml down -v --remove-orphans
