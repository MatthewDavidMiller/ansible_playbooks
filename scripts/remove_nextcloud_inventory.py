#!/usr/bin/env python3
"""Move an inventory off the retired Nextcloud, Paperless NGX, PostgreSQL and Redis settings.

The edit is textual, so comments, ordering, quoting, and !vault blocks in the
rest of the file stay exactly as they are. Nothing is written until --write is
given, and the script never prints a value from the file: it reports variable
names and line numbers only. See scripts/inventory_cleanup.py for the checks
it makes before writing.

It renames the variables that stay in use under homedrive's names:

  nextcloud_disk              -> data_disk
  nextcloud_disk_mount_path   -> data_disk_mount_path
  nextcloud_homelab_user      -> homedrive_main_user

and removes every nextcloud_*, paperless_*, postgres_* and redis_* setting the
roles used, the rclone "Nextcloud" remote's settings, the files-backup and
backup_destination settings, and the stack's entries in the route
dictionaries, container_dns.aliases, proxy_config, and container_service_names,
wherever the inventory still carries them.

By default it keeps the paths that retire_nextcloud.yml needs to find the data
and the Borg repository (nextcloud_path, paperless_path, postgres_path,
nextcloud_borg_backup_path). Run it again with --all after that playbook has
run. It refuses to rename a variable whose new name is already in the file,
and to write a file in which something still refers to a variable it would
remove or rename.
"""

from __future__ import annotations

import sys

import inventory_cleanup
from inventory_cleanup import _Loader  # noqa: F401 - used by the tests

ROUTE_NETWORK = "nextcloud_proxy_net"
BACKEND_NAMES = frozenset(
    {
        "postgres_backend",
        "redis_backend",
        "nextcloud_backend",
        "paperless_backend",
        "nextcloud_proxy",
        "paperless_proxy",
    }
)
ROUTE_ENTRIES = frozenset({"nextcloud_proxy_net", "paperless_proxy_net"})

SPEC = inventory_cleanup.Spec(
    service="nextcloud",
    removed_vars=(
        # The Nextcloud role
        "nextcloud_uid",
        "nextcloud_gid",
        "nextcloud_normalize_user_files_permissions",
        "nextcloud_user_files_directory_mode",
        "nextcloud_user_files_file_mode",
        "nextcloud_database_name",
        "nextcloud_db_user",
        "nextcloud_db_password",
        "nextcloud_admin_user",
        "nextcloud_admin_password",
        "nextcloud_trusted_domains",
        "nextcloud_dns_name",
        "nextcloud_paperless_backup_location",
        "nextcloud_backend_network_subnet",
        "nextcloud_image",
        "nextcloud_backup_hour",
        "nextcloud_backup_minute",
        "nextcloud_stack_deploy",
        "nextcloud_stack_enabled",
        # PostgreSQL and Redis
        "postgres_admin_user",
        "postgres_admin_password",
        "postgres_legacy_bootstrap_user",
        "postgres_legacy_bootstrap_password",
        "postgres_image",
        "redis_image",
        "password_minimum_length",
        "secret_key_minimum_length",
        # Paperless NGX
        "paperless_data_path",
        "paperless_media_path",
        "paperless_export_path",
        "paperless_consume_path",
        "paperless_database_name",
        "paperless_db_user",
        "paperless_db_password",
        "paperless_secret_key",
        "paperless_dns_name",
        "paperless_image",
        # The Borg backup of the Nextcloud files, and where backups go
        "backup_local",
        "backup_destination",
        "ssh_mount_path",
        "nextcloud_host",
        "nextcloud_backup_path",
        "backup_ssh_known_hosts",
        "borg_backup_hour",
        "borg_backup_minute",
        # The rclone "Nextcloud" remote
        "nextcloud_webdav_path",
        "nextcloud_webdav_user",
        "nextcloud_webdav_pass",
        "nextcloud_rclone_user",
        "nextcloud_rclone_pass",
    ),
    # Read by retire_nextcloud.yml to find what it removes (and what it must
    # not): kept until it has run.
    cleanup_vars=(
        "nextcloud_path",
        "paperless_path",
        "postgres_path",
        "nextcloud_borg_backup_path",
    ),
    all_help=(
        "also remove nextcloud_path, paperless_path, postgres_path and "
        "nextcloud_borg_backup_path (run after retire_nextcloud.yml)"
    ),
    route_network=ROUTE_NETWORK,
    extra_route_networks=("paperless_proxy_net", "nextcloud_container_net"),
    service_names=frozenset(
        {
            "postgres_container",
            "postgres_container.service",
            "redis_container",
            "redis_container.service",
            "nextcloud_container",
            "nextcloud_container.service",
            "paperless_ngx",
            "paperless_ngx.service",
        }
    ),
    dict_entries={
        "route_proxy_network_subnets": ROUTE_ENTRIES,
        "route_proxy_container_ips": ROUTE_ENTRIES,
        "route_proxy_traefik_ips": ROUTE_ENTRIES,
        "container_static_ips": BACKEND_NAMES,
        "aliases": BACKEND_NAMES,
    },
    proxy_alias="nextcloud_proxy",
    renames={
        "nextcloud_disk": "data_disk",
        "nextcloud_disk_mount_path": "data_disk_mount_path",
        "nextcloud_homelab_user": "homedrive_main_user",
    },
    guide="docs/variables.md (Obsolete variables)",
)


def main(argv: list[str] | None = None) -> int:
    return inventory_cleanup.main(SPEC, __doc__.split("\n\n")[0], argv)


if __name__ == "__main__":
    sys.exit(main())
