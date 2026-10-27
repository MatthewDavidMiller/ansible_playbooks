#!/usr/bin/env python3
"""Remove the retired Navidrome settings from an inventory YAML file.

The edit is textual, so comments, ordering, quoting, and !vault blocks in the
rest of the file stay exactly as they are. Nothing is written until --write is
given, and the script never prints a value from the file: it reports variable
names and line numbers only. See scripts/inventory_cleanup.py for the checks
it makes before writing.

Besides the navidrome_* variables, it removes Navidrome's entries from the
route dictionaries, container_dns.aliases, proxy_config, and
container_service_names, wherever an older inventory still carries them.

By default it keeps navidrome_path, which retire_navidrome.yml needs to
delete Navidrome's data directory when asked to. Run it again with --all
after that playbook has run.
"""

from __future__ import annotations

import sys

import inventory_cleanup
from inventory_cleanup import _Loader  # noqa: F401 - used by the tests

ROUTE_NETWORK = "navidrome_container_net"

SPEC = inventory_cleanup.Spec(
    service="navidrome",
    removed_vars=(
        "navidrome_local_music_path",
        "navidrome_backup_location",
        "navidrome_uid",
        "navidrome_gid",
        "navidrome_image",
    ),
    # Needed by retire_navidrome.yml to remove the data directory, so kept
    # until it has run.
    cleanup_vars=("navidrome_path",),
    all_help="also remove navidrome_path (run after retire_navidrome.yml)",
    route_network=ROUTE_NETWORK,
    service_names=frozenset({"navidrome_container", "navidrome_container.service"}),
    dict_entries={
        "route_proxy_network_subnets": frozenset({ROUTE_NETWORK}),
        "route_proxy_container_ips": frozenset({ROUTE_NETWORK}),
        "route_proxy_traefik_ips": frozenset({ROUTE_NETWORK}),
        "container_static_ips": frozenset({"navidrome_proxy"}),
        "aliases": frozenset({"navidrome_proxy"}),
    },
    proxy_alias="navidrome_proxy",
    guide="docs/guides/music-server-migration.md, section 5",
)


def main(argv: list[str] | None = None) -> int:
    return inventory_cleanup.main(SPEC, __doc__.split("\n\n")[0], argv)


if __name__ == "__main__":
    sys.exit(main())
