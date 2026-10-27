#!/usr/bin/env python3
"""Remove the retired Semaphore settings from an inventory YAML file.

The edit is textual, so comments, ordering, quoting, and !vault blocks in the
rest of the file stay exactly as they are. Nothing is written until --write is
given, and the script never prints a value from the file: it reports variable
names and line numbers only. See scripts/inventory_cleanup.py for the checks
it makes before writing.

By default it keeps semaphore_database_name and semaphore_db_user, which
retire_semaphore.yml needs to drop the database. Run it again with --all after
that playbook has run.
"""

from __future__ import annotations

import sys

import inventory_cleanup
from inventory_cleanup import _Loader  # noqa: F401 - used by the tests

ROUTE_NETWORK = "semaphore_container_net"

SPEC = inventory_cleanup.Spec(
    service="semaphore",
    removed_vars=(
        "semaphore_db_password",
        "semaphore_admin_name",
        "semaphore_admin_email",
        "semaphore_admin_password",
        "semaphore_encryption_key",
        "semaphore_known_hosts",
        "semaphore_backup_location",
        "semaphore_egress_network",
        "semaphore_image",
        # From before Semaphore moved into the shared PostgreSQL container;
        # nothing reads them any more, but an older inventory may still carry
        # them.
        "semaphore_postgres_path",
        "semaphore_database_user",
        "semaphore_database_user_password",
    ),
    # Needed by retire_semaphore.yml, so kept until it has run.
    cleanup_vars=("semaphore_database_name", "semaphore_db_user"),
    all_help="also remove semaphore_database_name and semaphore_db_user (run after retire_semaphore.yml)",
    route_network=ROUTE_NETWORK,
    service_names=frozenset({"semaphore", "semaphore.service"}),
    dict_entries={
        "route_proxy_network_subnets": frozenset({ROUTE_NETWORK}),
        "route_proxy_container_ips": frozenset({ROUTE_NETWORK}),
        "route_proxy_traefik_ips": frozenset({ROUTE_NETWORK}),
        "container_static_ips": frozenset({"semaphore_backend", "semaphore_proxy"}),
        "aliases": frozenset({"semaphore_backend", "semaphore_proxy", "semaphore_egress"}),
    },
    list_entries={"reverse_proxy_deferred_route_networks": frozenset({ROUTE_NETWORK})},
    proxy_alias="semaphore_proxy",
    guide="docs/guides/playbook-runner-migration.md, section 4",
)


def main(argv: list[str] | None = None) -> int:
    return inventory_cleanup.main(SPEC, __doc__.split("\n\n")[0], argv)


if __name__ == "__main__":
    sys.exit(main())
