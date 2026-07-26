"""Validation filters shared by maintained homelab roles."""

from __future__ import annotations

import ipaddress
import json
import re
from pathlib import PurePosixPath


_DIGEST_REF = re.compile(r"^\S+@sha256:[0-9a-f]{64}$")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def homelab_valid_ipv4_cidr(value: object, reject_default: bool = True) -> bool:
    try:
        network = ipaddress.ip_network(str(value), strict=True)
    except ValueError:
        return False
    if not isinstance(network, ipaddress.IPv4Network):
        return False
    return not (reject_default and network.prefixlen == 0)


def homelab_valid_ipv4_address(value: object) -> bool:
    try:
        return isinstance(ipaddress.ip_address(str(value)), ipaddress.IPv4Address)
    except ValueError:
        return False


def homelab_ip_in_network(address: object, network: object) -> bool:
    try:
        parsed_address = ipaddress.ip_address(str(address))
        parsed_network = ipaddress.ip_network(str(network), strict=True)
    except ValueError:
        return False
    return (
        isinstance(parsed_address, ipaddress.IPv4Address)
        and isinstance(parsed_network, ipaddress.IPv4Network)
        and parsed_address in parsed_network
        and parsed_address not in (parsed_network.network_address, parsed_network.broadcast_address)
    )


def homelab_container_assignable_ip(address: object, network: object) -> bool:
    """A host address Podman can hand to a container on this network.

    Podman claims the first host address of a network as the bridge gateway,
    so a container that requests it never starts.
    """
    if not homelab_ip_in_network(address, network):
        return False
    parsed_network = ipaddress.ip_network(str(network), strict=True)
    return ipaddress.ip_address(str(address)) != next(parsed_network.hosts())


def homelab_safe_absolute_path(value: object) -> bool:
    text = str(value)
    if not text or text.strip() != text or "\x00" in text:
        return False
    path = PurePosixPath(text)
    return path.is_absolute() and path != PurePosixPath("/") and ".." not in path.parts


def homelab_immutable_image(value: object) -> bool:
    return bool(_DIGEST_REF.fullmatch(str(value)))


def homelab_safe_name(value: object) -> bool:
    text = str(value)
    return text not in {".", ".."} and bool(_SAFE_NAME.fullmatch(text))


def _first_inspected_network(inspect_output: object) -> dict:
    """The single network entry `podman network inspect <name>` reports."""
    try:
        networks = json.loads(str(inspect_output))
    except (TypeError, ValueError) as exc:
        raise ValueError("podman network inspect did not return JSON") from exc
    if not isinstance(networks, list) or not networks:
        raise ValueError("podman network inspect returned no network entry")
    network = networks[0]
    if not isinstance(network, dict):
        raise ValueError("podman network inspect returned an unexpected entry")
    return network


def homelab_network_needs_replacement(
    inspect_output: object,
    subnet: object = "",
    require_internal: bool = True,
) -> bool:
    """Whether an existing Podman network must be torn down and recreated.

    Podman cannot convert a network to `--internal` or move it to a different
    subnet in place, so a network whose recorded state has drifted from the
    declared state is only fixable by replacement. Callers pass the stdout of a
    successful `podman network inspect`; an empty ``subnet`` means the network
    has no deterministic subnet and only the internal flag is enforced.
    """
    network = _first_inspected_network(inspect_output)

    # Podman 4 reports `internal`; older releases used `Internal`.
    is_internal = network.get("internal", network.get("Internal", False))
    if require_internal and not is_internal:
        return True

    declared_subnet = str(subnet).strip()
    if not declared_subnet:
        return False

    subnets = network.get("subnets") or []
    if not isinstance(subnets, list):
        raise ValueError("podman network inspect returned unexpected subnet data")
    configured = [
        entry.get("subnet") for entry in subnets if isinstance(entry, dict)
    ]
    return declared_subnet not in configured


class FilterModule:
    def filters(self) -> dict[str, object]:
        return {
            "homelab_valid_ipv4_cidr": homelab_valid_ipv4_cidr,
            "homelab_valid_ipv4_address": homelab_valid_ipv4_address,
            "homelab_ip_in_network": homelab_ip_in_network,
            "homelab_ip_in_subnet": homelab_ip_in_network,
            "homelab_container_assignable_ip": homelab_container_assignable_ip,
            "homelab_safe_absolute_path": homelab_safe_absolute_path,
            "homelab_immutable_image": homelab_immutable_image,
            "homelab_immutable_digest_ref": homelab_immutable_image,
            "homelab_safe_name": homelab_safe_name,
            "homelab_network_needs_replacement": homelab_network_needs_replacement,
        }
