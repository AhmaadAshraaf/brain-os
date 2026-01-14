#!/bin/bash
set -euo pipefail

# bulk_ingest.sh - Batch process PDFs in groups of 10 (VM Only)
# Usage: ./scripts/bulk_ingest.sh [source_dir] [batch_size]
#
# Moves PDFs from source directory to ingest watch directory in batches,
# waits for processing to complete, then processes next batch.

# Configuration
SOURCE_DIR="${1:-/home/ops/brain-os/data/raw}"
WATCH_DIR="/home/ops/brain-os/data/documents"
BATCH_SIZE="${2:-10}"
INGEST_CONTAINER="infra-ingest-1"
LOG_WAIT_TIME=5  # seconds to wait before checking logs
MAX_WAIT_TIME=300  # max seconds to wait for batch processing

echo "[INFO] =========================================="
echo "[INFO] Brain-OS Bulk Ingestion Script"
echo "[INFO] =========================================="
echo "[INFO] Source directory: ${SOURCE_DIR}"
echo "[INFO] Watch directory: ${WATCH_DIR}"
echo "[INFO] Batch size: ${BATCH_SIZE} files"
echo "[INFO] =========================================="

# Validate source directory exists
if [ ! -d "${SOURCE_DIR}" ]; then
    echo "[ERROR] Source directory does not exist: ${SOURCE_DIR}"
    exit 1
fi

# Validate watch directory exists
if [ ! -d "${WATCH_DIR}" ]; then
    echo "[ERROR] Watch directory does not exist: ${WATCH_DIR}"
    exit 1
fi

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker command not found. Is Docker installed?"
    exit 1
fi

# Check if ingest container exists
if ! docker ps -a --format '{{.Names}}' | grep -q "^${INGEST_CONTAINER}$"; then
    echo "[ERROR] Ingest container not found: ${INGEST_CONTAINER}"
    echo "[INFO] Start the stack first: make up-online"
    exit 1
fi

# Count total PDFs in source
TOTAL_PDFS=$(find "${SOURCE_DIR}" -maxdepth 1 -type f -iname "*.pdf" | wc -l)

if [ "${TOTAL_PDFS}" -eq 0 ]; then
    echo "[INFO] No PDF files found in ${SOURCE_DIR}"
    exit 0
fi

echo "[INFO] Found ${TOTAL_PDFS} PDF(s) to process"

# Calculate number of batches
BATCHES=$(( (TOTAL_PDFS + BATCH_SIZE - 1) / BATCH_SIZE ))
echo "[INFO] Will process in ${BATCHES} batch(es)"
echo ""

# Function to wait for ingestion completion
wait_for_ingestion() {
    local batch_num=$1
    local expected_files=$2

    echo "[INFO] Waiting ${LOG_WAIT_TIME}s for processing to start..."
    sleep ${LOG_WAIT_TIME}

    echo "[INFO] Monitoring ingest container logs..."
    local waited=0
    local completed=false

    while [ ${waited} -lt ${MAX_WAIT_TIME} ]; do
        # Check last 20 lines of logs for completion event
        if docker logs --tail 20 "${INGEST_CONTAINER}" 2>&1 | grep -q '"event":"ingest_service_completed"'; then
            # Extract the files_processed count from the most recent completion event
            local processed=$(docker logs --tail 20 "${INGEST_CONTAINER}" 2>&1 | \
                grep '"event":"ingest_service_completed"' | tail -1 | \
                grep -o '"files_processed":[0-9]*' | cut -d: -f2)

            if [ -n "${processed}" ] && [ "${processed}" -ge "${expected_files}" ]; then
                echo "[OK] Batch ${batch_num} processing completed (${processed} files)"
                completed=true
                break
            fi
        fi

        sleep 2
        waited=$((waited + 2))
    done

    if [ "${completed}" = false ]; then
        echo "[WARN] Batch ${batch_num} did not complete within ${MAX_WAIT_TIME}s"
        echo "[WARN] Check logs manually: docker logs ${INGEST_CONTAINER}"
        return 1
    fi

    return 0
}

# Process PDFs in batches
batch_num=0
processed_total=0
failed_batches=0

while [ ${processed_total} -lt ${TOTAL_PDFS} ]; do
    batch_num=$((batch_num + 1))

    echo "=========================================="
    echo "[INFO] Processing Batch ${batch_num}/${BATCHES}"
    echo "=========================================="

    # Get next batch of PDFs
    mapfile -t batch_files < <(find "${SOURCE_DIR}" -maxdepth 1 -type f -iname "*.pdf" | head -n ${BATCH_SIZE})

    if [ ${#batch_files[@]} -eq 0 ]; then
        echo "[INFO] No more files to process"
        break
    fi

    echo "[INFO] Moving ${#batch_files[@]} file(s) to watch directory..."

    # Move files to watch directory
    for pdf in "${batch_files[@]}"; do
        filename=$(basename "${pdf}")
        echo "  - ${filename}"
        mv "${pdf}" "${WATCH_DIR}/"
    done

    echo "[OK] Files moved to watch directory"

    # Restart ingest container to trigger processing
    echo "[INFO] Restarting ingest container..."
    docker restart "${INGEST_CONTAINER}" > /dev/null
    echo "[OK] Container restarted"

    # Wait for processing to complete
    if wait_for_ingestion ${batch_num} ${#batch_files[@]}; then
        processed_total=$((processed_total + ${#batch_files[@]}))
        echo "[INFO] Progress: ${processed_total}/${TOTAL_PDFS} files processed"
    else
        failed_batches=$((failed_batches + 1))
        echo "[ERROR] Batch ${batch_num} processing failed or timed out"
        echo "[INFO] Continuing with next batch..."
        processed_total=$((processed_total + ${#batch_files[@]}))
    fi

    echo ""
done

# Summary
echo "=========================================="
echo "[INFO] Bulk Ingestion Complete"
echo "=========================================="
echo "[INFO] Total files processed: ${processed_total}/${TOTAL_PDFS}"
if [ ${failed_batches} -gt 0 ]; then
    echo "[WARN] Failed/timed-out batches: ${failed_batches}"
    echo "[INFO] Check container logs: docker logs ${INGEST_CONTAINER}"
else
    echo "[OK] All batches completed successfully"
fi

# Final snapshot recommendation
echo ""
echo "[INFO] Recommendation: Create a snapshot to preserve this data"
echo "[INFO] Run: cd /home/ops/brain-os && ./scripts/snapshot_push.sh"
echo ""
