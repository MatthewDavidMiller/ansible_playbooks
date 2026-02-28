#!/bin/bash
#
# backup_proxmox_config.sh — Back up Proxmox node configuration to Nextcloud.
#
# Run on the Proxmox host. Requires rclone installed and configured with a
# 'Nextcloud' remote. See docs/guides/proxmox-setup.md for setup details.
#
# Setup:
#   1. Set RCLONE_DEST below to your Nextcloud remote path.
#   2. Add to root crontab on the Proxmox host, e.g.:
#        0 2 * * * /root/backup_proxmox_config.sh

set -euo pipefail

RCLONE_DEST="Nextcloud:<proxmox_backup_location>"
ARCHIVE="proxmox_config_$(date +%Y%m%d).tar.gz"
STAGING=$(mktemp -d)
LOG=/var/log/backup_proxmox_config.log

# Truncate log if it exceeds 10 MB
if [ -f "$LOG" ] && [ "$(stat -c%s "$LOG")" -gt 10485760 ]; then
    tail -c 5242880 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi

{
    echo "=== $(date) ==="
    tar -czf "$STAGING/$ARCHIVE" /etc/pve/
    rclone copy "$STAGING/$ARCHIVE" "$RCLONE_DEST"
    echo "Uploaded $ARCHIVE to $RCLONE_DEST"

    # Prune backups older than 30 days once there are at least 30 on the remote
    if [ "$(rclone ls "$RCLONE_DEST" | wc -l)" -ge 30 ]; then
        rclone delete --min-age 30d "$RCLONE_DEST"
        echo "Pruned old backups from $RCLONE_DEST"
    fi
} >> "$LOG" 2>&1

rm -rf "$STAGING"
