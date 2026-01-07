#!/bin/bash
set -euo pipefail

# snapshot_push.sh - Push Qdrant snapshot to Wasabi S3 (VM Only)
# Usage: ./scripts/snapshot_push.sh

source .env

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SNAPSHOT_NAME="brain_os_${TIMESTAMP}"
QDRANT_URL="http://${QDRANT_HOST:-localhost}:${QDRANT_PORT:-6333}"
COLLECTION="${QDRANT_COLLECTION:-brain_os}"

echo "[INFO] Starting snapshot process for collection: ${COLLECTION}"

# Step 1: Create snapshot via Qdrant API
echo "[INFO] Creating Qdrant snapshot..."
SNAPSHOT_RESPONSE=$(curl -s -X POST "${QDRANT_URL}/collections/${COLLECTION}/snapshots")
SNAPSHOT_FILE=$(echo "${SNAPSHOT_RESPONSE}" | jq -r '.result.name')

if [ -z "${SNAPSHOT_FILE}" ] || [ "${SNAPSHOT_FILE}" == "null" ]; then
    echo "[ERROR] Failed to create snapshot"
    echo "${SNAPSHOT_RESPONSE}"
    exit 1
fi

echo "[INFO] Snapshot created: ${SNAPSHOT_FILE}"

# Step 2: Download snapshot locally
echo "[INFO] Downloading snapshot..."
TEMP_DIR=$(mktemp -d)
curl -s -o "${TEMP_DIR}/${SNAPSHOT_FILE}" \
    "${QDRANT_URL}/collections/${COLLECTION}/snapshots/${SNAPSHOT_FILE}"

# Step 3: Upload to Wasabi S3
echo "[INFO] Uploading to Wasabi S3..."
aws s3 cp "${TEMP_DIR}/${SNAPSHOT_FILE}" \
    "s3://${WASABI_BUCKET}/snapshots/${SNAPSHOT_NAME}.snapshot" \
    --endpoint-url "${WASABI_ENDPOINT}"

# Step 4: Update latest pointer
echo "${SNAPSHOT_NAME}" | aws s3 cp - \
    "s3://${WASABI_BUCKET}/snapshots/LATEST" \
    --endpoint-url "${WASABI_ENDPOINT}"

# Step 5: Cleanup
rm -rf "${TEMP_DIR}"
curl -s -X DELETE "${QDRANT_URL}/collections/${COLLECTION}/snapshots/${SNAPSHOT_FILE}"

echo "[SUCCESS] Snapshot pushed: ${SNAPSHOT_NAME}"
echo "[INFO] S3 path: s3://${WASABI_BUCKET}/snapshots/${SNAPSHOT_NAME}.snapshot"
