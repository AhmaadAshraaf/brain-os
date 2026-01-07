#!/bin/bash
set -euo pipefail

# restore.sh - Restore Qdrant from a specific snapshot
# Usage: ./scripts/restore.sh <snapshot_name>

source .env

SNAPSHOT_NAME="${1:-}"

if [ -z "${SNAPSHOT_NAME}" ]; then
    echo "Usage: ./scripts/restore.sh <snapshot_name>"
    echo ""
    echo "Available snapshots:"
    aws s3 ls "s3://${WASABI_BUCKET}/snapshots/" \
        --endpoint-url "${WASABI_ENDPOINT}" | grep ".snapshot" | awk '{print $4}' | sed 's/.snapshot$//'
    exit 1
fi

DATA_DIR="./data/qdrant_snapshot"

echo "[INFO] Restoring snapshot: ${SNAPSHOT_NAME}"

# Step 1: Stop any running services
echo "[INFO] Stopping services..."
make clean 2>/dev/null || true

# Step 2: Clear existing data
echo "[INFO] Clearing existing data..."
rm -rf "${DATA_DIR:?}"/*

# Step 3: Download specified snapshot
TEMP_FILE=$(mktemp)
echo "[INFO] Downloading snapshot..."
aws s3 cp "s3://${WASABI_BUCKET}/snapshots/${SNAPSHOT_NAME}.snapshot" "${TEMP_FILE}" \
    --endpoint-url "${WASABI_ENDPOINT}"

# Step 4: Extract
mkdir -p "${DATA_DIR}"
echo "[INFO] Extracting snapshot..."
tar -xzf "${TEMP_FILE}" -C "${DATA_DIR}" --strip-components=1 2>/dev/null || \
    unzip -o "${TEMP_FILE}" -d "${DATA_DIR}"

# Step 5: Cleanup
rm -f "${TEMP_FILE}"

echo "[SUCCESS] Restored snapshot: ${SNAPSHOT_NAME}"
echo "[INFO] Run 'make up-offline' to start with this data"
