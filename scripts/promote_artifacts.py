#!/usr/bin/env python3
"""Resolve, verify, scan, and optionally mirror approved container artifacts."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCK_FILE = REPO_ROOT / "artifacts" / "containers.lock.yml"
TOOLING_GUIDE = REPO_ROOT / "docs" / "guides" / "container-image-updates.md"
FALLBACK_TOOL_IMAGES = {
    "skopeo": "quay.io/skopeo/stable@sha256:a5a222322c25987ad9fcdf005306c90c5a84db66a3b3dcef98f5f9af4ea15d3f",
    "cosign": "ghcr.io/sigstore/cosign/cosign@sha256:774391ac9f0c137ee419ce56522df5fd3b1f52be90c5b77e97f7c053bdd67a67",
    "trivy": "public.ecr.aws/aquasecurity/trivy@sha256:bcc376de8d77cfe086a917230e818dc9f8528e3c852f7b1aff648949b6258d1c",
}
ANNOUNCED_FALLBACKS: set[str] = set()


def run(argv: list[str], *, capture_output: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def container_engine() -> str | None:
    for candidate in ("podman", "docker"):
        if shutil.which(candidate):
            return candidate
    return None


def add_mount(argv: list[str], source: Path, target: str, *, read_only: bool = True) -> None:
    if not source.exists():
        return
    mode = "ro" if read_only else "rw"
    argv.extend(["-v", f"{source}:{target}:{mode}"])


def docker_config_uses_external_helpers(config_path: Path) -> bool:
    if not config_path.exists():
        return False
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("credsStore") or data.get("credHelpers"))


def resolve_tool_command(name: str) -> tuple[list[str], str]:
    local_binary = shutil.which(name)
    if local_binary is not None:
        return [local_binary], f"local binary ({local_binary})"

    engine = container_engine()
    if engine is None:
        raise SystemExit(
            f"Required tool not available: {name}. Install it locally or ensure podman/docker is available "
            f"for the pinned container fallback. See {TOOLING_GUIDE}."
        )

    argv = [engine, "run", "--rm"]
    if engine == "podman":
        argv.extend(["--security-opt", "label=disable"])

    docker_config = Path.home() / ".docker" / "config.json"
    if not docker_config_uses_external_helpers(docker_config):
        add_mount(argv, Path.home() / ".docker", "/root/.docker")
    add_mount(argv, Path.home() / ".config" / "containers", "/root/.config/containers")

    trivy_cache_dir = Path.home() / ".cache" / "trivy"
    if name == "trivy":
        trivy_cache_dir.mkdir(parents=True, exist_ok=True)
        add_mount(argv, trivy_cache_dir, "/root/.cache/trivy", read_only=False)

    argv.append(FALLBACK_TOOL_IMAGES[name])
    return argv, f"container fallback via {engine} ({FALLBACK_TOOL_IMAGES[name]})"


def tool_command(name: str) -> list[str]:
    argv, description = resolve_tool_command(name)
    if description.startswith("container fallback") and name not in ANNOUNCED_FALLBACKS:
        ANNOUNCED_FALLBACKS.add(name)
        print(f"[{name}] using {description}", file=sys.stderr)
    return argv


def required_tools(*, skip_signature_verify: bool, skip_scan: bool) -> list[str]:
    tools = ["skopeo"]
    if not skip_signature_verify:
        tools.append("cosign")
    if not skip_scan:
        tools.append("trivy")
    return tools


def print_tool_status(*, skip_signature_verify: bool, skip_scan: bool) -> None:
    for name in required_tools(skip_signature_verify=skip_signature_verify, skip_scan=skip_scan):
        _, description = resolve_tool_command(name)
        print(f"{name}: {description}")


def load_lock_file(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict) or "artifact_locked_images" not in data:
        raise SystemExit(f"Invalid lock file format: {path}")
    return data


def resolve_digest(upstream_ref: str) -> str:
    result = run(
        [
            *tool_command("skopeo"),
            "inspect",
            "--format",
            "{{.Digest}}",
            f"docker://{upstream_ref}",
        ]
    )
    digest = result.stdout.strip()
    if not digest.startswith("sha256:"):
        raise SystemExit(f"Failed to resolve digest for {upstream_ref}: {digest!r}")
    return digest


def to_digest_ref(image_ref: str, digest: str) -> str:
    if "@" in image_ref:
        image_name = image_ref.rsplit("@", 1)[0]
    else:
        last_slash = image_ref.rfind("/")
        last_colon = image_ref.rfind(":")
        if last_colon > last_slash:
            image_name = image_ref[:last_colon]
        else:
            image_name = image_ref
    return f"{image_name}@{digest}"


def signature_verification_args(entry: dict, service: str) -> list[str]:
    identity = entry.get("signature_identity")
    identity_regexp = entry.get("signature_identity_regexp")
    oidc_issuer = entry.get("signature_oidc_issuer")
    oidc_issuer_regexp = entry.get("signature_oidc_issuer_regexp")

    if identity and identity_regexp:
        raise SystemExit(
            f"{service}: set only one of signature_identity or signature_identity_regexp in the lock file"
        )
    if oidc_issuer and oidc_issuer_regexp:
        raise SystemExit(
            f"{service}: set only one of signature_oidc_issuer or signature_oidc_issuer_regexp in the lock file"
        )

    argv: list[str] = []
    if identity:
        argv.extend(["--certificate-identity", identity])
    elif identity_regexp:
        argv.extend(["--certificate-identity-regexp", identity_regexp])
    else:
        raise SystemExit(
            f"{service}: signature_required is true but no signature_identity or "
            "signature_identity_regexp is recorded in the lock file"
        )

    if oidc_issuer:
        argv.extend(["--certificate-oidc-issuer", oidc_issuer])
    elif oidc_issuer_regexp:
        argv.extend(["--certificate-oidc-issuer-regexp", oidc_issuer_regexp])
    else:
        raise SystemExit(
            f"{service}: signature_required is true but no signature_oidc_issuer or "
            "signature_oidc_issuer_regexp is recorded in the lock file"
        )

    return argv


def verify_signature(image_ref: str, entry: dict, service: str) -> None:
    run(
        [
            *tool_command("cosign"),
            "verify",
            *signature_verification_args(entry, service),
            image_ref,
        ],
        capture_output=False,
    )


def scan_image(image_ref: str) -> None:
    run(
        [
            *tool_command("trivy"),
            "image",
            "--scanners",
            "vuln",
            "--image-src",
            "remote",
            "--ignore-unfixed",
            "--severity",
            "HIGH,CRITICAL",
            "--exit-code",
            "1",
            image_ref,
        ],
        capture_output=False,
    )


def mirror_image(upstream_ref: str, internal_ref: str, digest: str) -> None:
    mirror_tag = f"sha-{digest[7:19]}"
    run(
        [
            *tool_command("skopeo"),
            "copy",
            "--all",
            f"docker://{upstream_ref}",
            f"docker://{internal_ref}:{mirror_tag}",
        ],
        capture_output=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK_FILE)
    parser.add_argument("--registry", help="Optional registry host to mirror approved digests into, e.g. registry.example.internal")
    parser.add_argument("--service", action="append", help="Only process the named service(s)")
    parser.add_argument("--write", action="store_true", help="Write updated digests back to the lock file")
    parser.add_argument(
        "--check-tools",
        action="store_true",
        help="Only report whether the required tools are available locally or via the pinned container fallback",
    )
    parser.add_argument(
        "--skip-signature-verify",
        action="store_true",
        help="Skip cosign verification even when signature_required is true",
    )
    parser.add_argument(
        "--skip-scan",
        action="store_true",
        help="Skip trivy vulnerability scanning",
    )
    args = parser.parse_args()

    if args.check_tools:
        print_tool_status(skip_signature_verify=args.skip_signature_verify, skip_scan=args.skip_scan)
        return 0

    for tool_name in required_tools(skip_signature_verify=args.skip_signature_verify, skip_scan=args.skip_scan):
        resolve_tool_command(tool_name)

    lock_data = load_lock_file(args.lock_file)
    images = lock_data["artifact_locked_images"]
    selected = set(args.service or images.keys())

    for service in selected:
        if service not in images:
            raise SystemExit(f"Unknown service in lock file: {service}")

    for service in selected:
        entry = images[service]
        upstream_ref = entry["upstream_ref"]
        digest = resolve_digest(upstream_ref)
        print(f"[{service}] upstream={upstream_ref}")
        print(f"[{service}] digest={digest}")
        digest_ref = to_digest_ref(upstream_ref, digest)
        print(f"[{service}] approved={digest_ref}")

        if args.registry:
            internal_ref = f"{args.registry}/{entry['internal_repo']}"
            print(f"[{service}] mirror={internal_ref}@{digest}")

        if entry.get("signature_required", False) and not args.skip_signature_verify:
            verify_signature(digest_ref, entry, service)

        if not args.skip_scan:
            scan_image(digest_ref)

        if args.registry:
            mirror_image(digest_ref, internal_ref, digest)

        if args.write:
            entry["approved_digest"] = digest
            if args.registry:
                entry["notes"] = f"Approved via scripts/promote_artifacts.py and mirrored to {args.registry}"
            else:
                entry["notes"] = "Approved via scripts/promote_artifacts.py"

    if args.write:
        with args.lock_file.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(lock_data, handle, sort_keys=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
