#!/bin/bash
set -euo pipefail

# monitor_ollama_ram.sh - Monitor Ollama container RAM usage and alert on spikes (VM Only)
# Usage: ./scripts/monitor_ollama_ram.sh [threshold_gb] [check_interval]
#
# Can be run as a daemon or via cron:
#   */5 * * * * /home/ops/brain-os/scripts/monitor_ollama_ram.sh 6 >> /var/log/ollama_monitor.log 2>&1

# Configuration
OLLAMA_CONTAINER="${OLLAMA_CONTAINER:-infra-ollama-1}"
RAM_THRESHOLD_GB="${1:-8}"  # Alert if RAM exceeds this (default: 8GB)
CHECK_INTERVAL="${2:-0}"    # Seconds between checks (0 = run once, for cron)
ALERT_LOG="/var/log/ollama_ram_alerts.log"

# Convert GB to bytes for comparison
RAM_THRESHOLD_BYTES=$((RAM_THRESHOLD_GB * 1024 * 1024 * 1024))

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Ollama RAM monitoring..."
echo "[INFO] Container: ${OLLAMA_CONTAINER}"
echo "[INFO] Threshold: ${RAM_THRESHOLD_GB}GB (${RAM_THRESHOLD_BYTES} bytes)"
echo "[INFO] Check interval: ${CHECK_INTERVAL}s (0 = single check)"

# Function to check RAM usage
check_ram_usage() {
    # Check if container exists and is running
    if ! docker ps --format '{{.Names}}' | grep -q "^${OLLAMA_CONTAINER}$"; then
        echo "[WARN] Container ${OLLAMA_CONTAINER} is not running"
        return 1
    fi

    # Get memory usage in bytes (docker stats output format: "used / limit")
    local stats=$(docker stats --no-stream --format "{{.MemUsage}}" "${OLLAMA_CONTAINER}")
    local mem_used=$(echo "${stats}" | awk '{print $1}')
    local mem_unit=$(echo "${mem_used}" | grep -o '[A-Za-z]*$')
    local mem_value=$(echo "${mem_used}" | grep -o '[0-9.]*')

    # Convert to bytes based on unit
    local mem_bytes=0
    case "${mem_unit}" in
        GiB|GB)
            mem_bytes=$(echo "${mem_value} * 1024 * 1024 * 1024" | bc | cut -d. -f1)
            ;;
        MiB|MB)
            mem_bytes=$(echo "${mem_value} * 1024 * 1024" | bc | cut -d. -f1)
            ;;
        KiB|KB)
            mem_bytes=$(echo "${mem_value} * 1024" | bc | cut -d. -f1)
            ;;
        B)
            mem_bytes=$(echo "${mem_value}" | cut -d. -f1)
            ;;
        *)
            echo "[ERROR] Unknown memory unit: ${mem_unit}"
            return 1
            ;;
    esac

    # Calculate percentage of threshold
    local threshold_pct=$(echo "scale=1; (${mem_bytes} / ${RAM_THRESHOLD_BYTES}) * 100" | bc)

    # Current usage in human-readable format
    local mem_gb=$(echo "scale=2; ${mem_bytes} / 1024 / 1024 / 1024" | bc)

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] RAM: ${mem_gb}GB / ${RAM_THRESHOLD_GB}GB (${threshold_pct}%)"

    # Alert if threshold exceeded
    if [ "${mem_bytes}" -gt "${RAM_THRESHOLD_BYTES}" ]; then
        local alert_msg="[ALERT] Ollama RAM spike detected!"
        local alert_details="  Container: ${OLLAMA_CONTAINER}
  Current usage: ${mem_gb}GB
  Threshold: ${RAM_THRESHOLD_GB}GB
  Exceeded by: $(echo "${mem_gb} - ${RAM_THRESHOLD_GB}" | bc)GB
  Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"

        echo "${alert_msg}"
        echo "${alert_details}"

        # Log to alert file
        {
            echo "=========================================="
            echo "${alert_msg}"
            echo "${alert_details}"
            echo "=========================================="
        } >> "${ALERT_LOG}"

        # Optional: Send alert notification (uncomment and configure)
        # send_alert_notification "${alert_msg}" "${alert_details}"

        return 2  # Return code 2 = threshold exceeded
    fi

    return 0  # Return code 0 = within threshold
}

# Function to send alert notifications (placeholder)
send_alert_notification() {
    local subject="$1"
    local body="$2"

    # Example integrations (uncomment and configure as needed):

    # Slack webhook
    # curl -X POST -H 'Content-type: application/json' \
    #   --data "{\"text\":\"${subject}\n${body}\"}" \
    #   "${SLACK_WEBHOOK_URL}"

    # Discord webhook
    # curl -X POST -H 'Content-type: application/json' \
    #   --data "{\"content\":\"${subject}\n\`\`\`${body}\`\`\`\"}" \
    #   "${DISCORD_WEBHOOK_URL}"

    # Email (requires mailutils)
    # echo "${body}" | mail -s "${subject}" admin@example.com

    # Telegram bot
    # curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    #   -d "chat_id=${TELEGRAM_CHAT_ID}" \
    #   -d "text=${subject}\n${body}"

    echo "[INFO] Alert notification sent (configure send_alert_notification() to enable)"
}

# Main monitoring loop
if [ "${CHECK_INTERVAL}" -eq 0 ]; then
    # Single check (for cron)
    check_ram_usage
    exit_code=$?
    exit ${exit_code}
else
    # Continuous monitoring
    echo "[INFO] Starting continuous monitoring (Ctrl+C to stop)..."
    while true; do
        check_ram_usage
        sleep "${CHECK_INTERVAL}"
    done
fi
