"""Validation filters shared by maintained homelab roles."""

from __future__ import annotations

import ipaddress
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


class FilterModule:
    def filters(self) -> dict[str, object]:
        return {
            "homelab_valid_ipv4_cidr": homelab_valid_ipv4_cidr,
            "homelab_valid_ipv4_address": homelab_valid_ipv4_address,
            "homelab_ip_in_network": homelab_ip_in_network,
            "homelab_ip_in_subnet": homelab_ip_in_network,
            "homelab_safe_absolute_path": homelab_safe_absolute_path,
            "homelab_immutable_image": homelab_immutable_image,
            "homelab_immutable_digest_ref": homelab_immutable_image,
            "homelab_safe_name": homelab_safe_name,
        }
