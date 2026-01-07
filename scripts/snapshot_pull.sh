#!/bin/bash
set -euo pipefail

# snapshot_pull.sh - Pull latest Qdrant snapshot from Wasabi S3 (Laptop)
# Usage: ./scripts/snapshot_pull.sh

source .env

DATA_DIR="./data/qdrant_snapshot"
COLLECTION="${QDRANT_COLLECTION:-brain_os}"

echo "[INFO] Pulling latest snapshot from Wasabi S3..."

# Step 1: Get latest snapshot name
LATEST=$(aws s3 cp "s3://${WASABI_BUCKET}/snapshots/LATEST" - \
    --endpoint-url "${WASABI_ENDPOINT}")

if [ -z "${LATEST}" ]; then
    echo "[ERROR] No LATEST pointer found in S3"
    exit 1
fi

echo "[INFO] Latest snapshot: ${LATEST}"

# Step 2: Create data directory
mkdir -p "${DATA_DIR}"

# Step 3: Download snapshot
TEMP_FILE=$(mktemp)
echo "[INFO] Downloading snapshot..."
aws s3 cp "s3://${WASABI_BUCKET}/snapshots/${LATEST}.snapshot" "${TEMP_FILE}" \
    --endpoint-url "${WASABI_ENDPOINT}"

# Step 4: Extract to data directory
echo "[INFO] Extracting snapshot to ${DATA_DIR}..."
tar -xzf "${TEMP_FILE}" -C "${DATA_DIR}" --strip-components=1 2>/dev/null || \
    unzip -o "${TEMP_FILE}" -d "${DATA_DIR}"

# Step 5: Cleanup
rm -f "${TEMP_FILE}"

echo "[SUCCESS] Snapshot restored to ${DATA_DIR}"
echo "[INFO] Run 'make up-offline' to start with this data"
