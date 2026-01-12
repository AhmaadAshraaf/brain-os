#!/bin/bash
set -euo pipefail

# setup.sh - Initial setup for Brain-OS
# Usage: ./scripts/setup.sh

echo "[INFO] Setting up Brain-OS..."

# Step 1: Check prerequisites
echo "[INFO] Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker is not installed"
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    echo "[ERROR] Docker Compose is not installed"
    exit 1
fi

echo "[OK] Docker and Docker Compose found"

# Step 2: Create .env from example if not exists
if [ ! -f .env ]; then
    echo "[INFO] Creating .env from .env.example..."
    cp .env.example .env
    echo "[WARN] Please edit .env with your configuration"
else
    echo "[OK] .env already exists"
fi

# Step 3: Create data directories
echo "[INFO] Creating data directories..."
mkdir -p data/documents
mkdir -p data/qdrant_snapshot

# Step 4: Pull required Docker images
echo "[INFO] Pulling Docker images..."
docker pull qdrant/qdrant:latest
docker pull ollama/ollama:latest
docker pull prom/prometheus:latest

# Step 5: Pull default Ollama model
echo "[INFO] Pulling default Ollama model..."
docker run --rm ollama/ollama pull llama3.1:8b || echo "[WARN] Could not pull model, will pull on first run"

echo ""
echo "[SUCCESS] Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your Wasabi S3 credentials"
echo "  2. Run 'make up-online' (VM) or 'make up-offline' (Laptop)"
