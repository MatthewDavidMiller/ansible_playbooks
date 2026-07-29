#!/bin/bash
#
# backup_proxmox_config.sh — Back up Proxmox node configuration to Nextcloud.
#
# Run on the Proxmox host. Requires rclone installed and configured with a
# 'Nextcloud' remote. See docs/guides/proxmox-setup.md for setup details.
#
# Setup:
#   1. Set RCLONE_DEST in root's crontab or a root-only environment file.
#   2. Add to root crontab on the Proxmox host, e.g.:
#        RCLONE_DEST=Nextcloud:backups/proxmox
#        0 2 * * * /root/backup_proxmox_config.sh

set -Eeuo pipefail

umask 077
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL=C

RCLONE_DEST=${RCLONE_DEST:-}
RETENTION_DAYS=${PROXMOX_BACKUP_RETENTION_DAYS:-30}
ARCHIVE="proxmox_config_$(date +%Y%m%d).tar.gz"
LOG=/var/log/backup_proxmox_config.log
LOCK_FILE=/run/lock/proxmox-config-backup.lock

if [[ -z "$RCLONE_DEST" || "$RCLONE_DEST" != *:* || "$RCLONE_DEST" == *'<'* || "$RCLONE_DEST" == *'>'* ]]; then
    echo "ERROR: Set RCLONE_DEST to a configured rclone remote path (for example Nextcloud:backups/proxmox)." >&2
    exit 2
fi
if [[ ! "$RETENTION_DAYS" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: PROXMOX_BACKUP_RETENTION_DAYS must be a positive integer." >&2
    exit 2
fi
if ! RCLONE_BIN=$(command -v rclone); then
    echo "ERROR: rclone is not installed or is not available on PATH." >&2
    exit 2
fi

exec 9>"$LOCK_FILE"
if ! flock --nonblock 9; then
    echo "INFO: Another Proxmox configuration backup is already running." >&2
    exit 0
fi

STAGING=$(mktemp -d /tmp/proxmox-config-backup.XXXXXX)
cleanup() {
    local exit_status=$?
    trap - EXIT
    if ! rm -rf -- "$STAGING"; then
        echo "ERROR: Failed to remove private backup staging directory $STAGING." >&2
        exit_status=1
    fi
    exit "$exit_status"
}
trap cleanup EXIT

# Truncate log if it exceeds 10 MB
if [[ -f "$LOG" && "$(stat -c%s "$LOG")" -gt 10485760 ]]; then
    tail -c 5242880 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi

{
    echo "=== $(date) ==="
    tar -C / -czf "$STAGING/$ARCHIVE" etc/pve
    "$RCLONE_BIN" copyto "$STAGING/$ARCHIVE" "$RCLONE_DEST/$ARCHIVE"
    echo "Uploaded $ARCHIVE to $RCLONE_DEST"

    # Restrict retention to this script's top-level archives. Never delete
    # unrelated files that happen to share the configured remote directory.
    "$RCLONE_BIN" delete "$RCLONE_DEST" \
        --min-age "${RETENTION_DAYS}d" \
        --max-depth 1 \
        --include 'proxmox_config_*.tar.gz'
    echo "Pruned Proxmox configuration archives older than $RETENTION_DAYS days"
} >> "$LOG" 2>&1
