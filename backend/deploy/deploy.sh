#!/usr/bin/env bash
# Deploy script for aegis backend with automatic rollback.
# Run on the VM via SSH from GitHub Actions.
set -euo pipefail

BINARY_PATH="/usr/local/bin/aegis"
BACKUP_PATH="/usr/local/bin/aegis-backup"
NEW_BINARY="/tmp/aegis-new"
HEALTH_URL="http://localhost:8080/healthz"
MAX_RETRIES=5
RETRY_DELAY=1

log() { echo "[deploy] $1"; }
err() { echo "[deploy] ERROR: $1" >&2; }

health_check() {
    for i in $(seq 1 $MAX_RETRIES); do
        if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
            return 0
        fi
        log "Health check attempt $i/$MAX_RETRIES failed, retrying in ${RETRY_DELAY}s..."
        sleep $RETRY_DELAY
    done
    return 1
}

rollback() {
    err "Deployment failed, rolling back..."
    if [[ -f "$BACKUP_PATH" ]]; then
        sudo systemctl stop aegis || true
        sudo mv "$BACKUP_PATH" "$BINARY_PATH"
        sudo systemctl start aegis
        log "Rollback complete, waiting for health check..."
        if health_check; then
            log "Rollback successful, service is healthy"
        else
            err "Rollback health check failed - manual intervention required"
            exit 1
        fi
    else
        err "No backup found at $BACKUP_PATH - manual intervention required"
        exit 1
    fi
    exit 1
}

# Validate new binary exists
if [[ ! -f "$NEW_BINARY" ]]; then
    err "New binary not found at $NEW_BINARY"
    exit 1
fi

log "Starting deployment..."

# Backup current binary (if exists)
if [[ -f "$BINARY_PATH" ]]; then
    log "Backing up current binary to $BACKUP_PATH"
    sudo cp "$BINARY_PATH" "$BACKUP_PATH"
fi

# Stop service, swap binary, start service (minimize downtime)
log "Stopping service..."
sudo systemctl stop aegis

log "Installing new binary..."
sudo mv "$NEW_BINARY" "$BINARY_PATH"
sudo chmod +x "$BINARY_PATH"

log "Starting service..."
sudo systemctl start aegis

# Health check
log "Waiting for service to start..."
sleep 2

if health_check; then
    log "Deployment successful! Health check passed."
    # Clean up backup after successful deployment (optional, keep for manual rollback)
    # sudo rm -f "$BACKUP_PATH"
else
    rollback
fi
