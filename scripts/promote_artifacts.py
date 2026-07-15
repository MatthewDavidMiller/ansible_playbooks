#!/usr/bin/env python3
"""Resolve, verify, scan, and optionally mirror approved container artifacts."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCK_FILE = REPO_ROOT / "artifacts" / "containers.lock.yml"
DEFAULT_SCAN_LOG = REPO_ROOT / "logs" / "container-vulnerability-findings.log"
DEFAULT_TRIVY_IGNORE_FILE = REPO_ROOT / "logs" / ".trivyignore"
DEFAULT_TRIVY_VEX_FILE = REPO_ROOT / "logs" / "trivy-vex.json"
DEFAULT_CRITICAL_ACCEPTANCE_FILE = REPO_ROOT / "logs" / "vulnerability-acceptance.yml"
TOOLING_GUIDE = REPO_ROOT / "docs" / "guides" / "container-image-updates.md"
SCAN_SEVERITIES = "MEDIUM,HIGH,CRITICAL"
NO_NEWER_IMAGE_EXCEPTION = "no_newer_upstream_image"
MAX_EXCEPTION_DAYS = 30
MINIMUM_IMAGE_AGE_HOURS = 48
FALLBACK_TOOL_IMAGES = {
    "skopeo": "quay.io/skopeo/stable@sha256:c7d3c512612f52805023cd38351081dad7e2729fc13d14b701e47c7c8bdd6615",
    "cosign": "ghcr.io/sigstore/cosign/cosign@sha256:6bbe0d281d955c79f85b325f0f7e651c1bcab5a4fa4ad4903d74955178a3b2eb",
    "trivy": "public.ecr.aws/aquasecurity/trivy@sha256:016eae51fdcf989332a5404af7e8f625cd5d95d7c0907a221d080a996f556500",
}
ANNOUNCED_FALLBACKS: set[str] = set()


@dataclass(frozen=True)
class ScanResult:
    finding_count: int
    non_critical_count: int
    critical_ids: frozenset[str]


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

    argv = [
        engine,
        "run",
        "--rm",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=256m",
    ]
    if name != "trivy":
        argv.extend(["--tmpfs", "/root/.cache:rw,noexec,nosuid,nodev,size=128m"])
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
        add_mount(argv, REPO_ROOT, str(REPO_ROOT))

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


def parse_policy_date(value: object, field: str, service: str) -> date:
    if not isinstance(value, str):
        raise SystemExit(f"{service}: {field} must be an ISO date (YYYY-MM-DD)")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"{service}: {field} must be an ISO date (YYYY-MM-DD)") from exc


def validate_exception_metadata(entry: dict, service: str, *, today: date | None = None) -> None:
    exception = entry.get("vulnerability_exception")
    if exception is None:
        return
    if exception != NO_NEWER_IMAGE_EXCEPTION:
        raise SystemExit(f"{service}: unknown vulnerability_exception: {exception}")

    current_date = today or date.today()
    reviewed = parse_policy_date(entry.get("vulnerability_exception_reviewed_on"), "vulnerability_exception_reviewed_on", service)
    expires = parse_policy_date(entry.get("vulnerability_exception_expires_on"), "vulnerability_exception_expires_on", service)
    if reviewed > current_date:
        raise SystemExit(f"{service}: vulnerability exception review date is in the future")
    if expires < current_date:
        raise SystemExit(f"{service}: vulnerability exception expired on {expires.isoformat()}")
    if expires < reviewed or (expires - reviewed).days > MAX_EXCEPTION_DAYS:
        raise SystemExit(f"{service}: vulnerability exception may cover at most {MAX_EXCEPTION_DAYS} days")


def load_critical_acceptances(path: Path, *, today: date | None = None) -> set[tuple[str, str, str]]:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    records = data.get("accepted_critical_vulnerabilities") if isinstance(data, dict) else None
    if not isinstance(records, list):
        raise SystemExit(f"Invalid critical vulnerability acceptance file: {path}")

    current_date = today or date.today()
    accepted: set[tuple[str, str, str]] = set()
    for index, record in enumerate(records, start=1):
        label = f"{path}: entry {index}"
        if not isinstance(record, dict):
            raise SystemExit(f"{label} must be a mapping")
        required = ("service", "image_digest", "vulnerability_id", "reason", "compensating_controls", "expires_on")
        missing = [field for field in required if not record.get(field)]
        if missing:
            raise SystemExit(f"{label} is missing required fields: {', '.join(missing)}")
        if not isinstance(record["compensating_controls"], list) or not all(
            isinstance(control, str) and control.strip() for control in record["compensating_controls"]
        ):
            raise SystemExit(f"{label}: compensating_controls must be a non-empty list of strings")
        expires = parse_policy_date(record["expires_on"], "expires_on", label)
        if expires < current_date or (expires - current_date).days > MAX_EXCEPTION_DAYS:
            raise SystemExit(f"{label}: expires_on must be within the next {MAX_EXCEPTION_DAYS} days")
        digest = record["image_digest"]
        if not isinstance(digest, str) or not digest.startswith("sha256:") or len(digest) != 71:
            raise SystemExit(f"{label}: image_digest must be a full sha256 digest")
        accepted.add((str(record["service"]), digest, str(record["vulnerability_id"])))
    return accepted


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


def inspect_image_created(upstream_ref: str) -> datetime:
    result = run([*tool_command("skopeo"), "inspect", f"docker://{upstream_ref}"])
    try:
        created_value = json.loads(result.stdout)["Created"]
        created = datetime.fromisoformat(str(created_value).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Failed to read image creation time for {upstream_ref}") from exc
    if created.tzinfo is None:
        raise SystemExit(f"Image creation time for {upstream_ref} has no timezone")
    return created.astimezone(timezone.utc)


def validate_minimum_image_age(
    created: datetime,
    service: str,
    *,
    now: datetime | None = None,
) -> None:
    current_time = now or datetime.now(timezone.utc)
    minimum_age = timedelta(hours=MINIMUM_IMAGE_AGE_HOURS)
    if current_time - created < minimum_age:
        eligible_at = created + minimum_age
        raise SystemExit(
            f"{service}: image is younger than {MINIMUM_IMAGE_AGE_HOURS} hours; "
            f"eligible after {eligible_at.isoformat()}"
        )


def critical_findings_are_preexisting(
    candidate_ids: list[str],
    currently_approved: ScanResult | None,
) -> bool:
    return bool(currently_approved) and set(candidate_ids).issubset(currently_approved.critical_ids)


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


def parse_trivy_result(output: str, service: str) -> ScanResult:
    try:
        report = json.loads(output)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{service}: Trivy returned invalid JSON") from exc
    vulnerabilities = [
        vulnerability
        for result in report.get("Results", [])
        for vulnerability in (result.get("Vulnerabilities") or [])
    ]
    critical_ids = frozenset(
        str(vulnerability.get("VulnerabilityID"))
        for vulnerability in vulnerabilities
        if vulnerability.get("Severity") == "CRITICAL" and vulnerability.get("VulnerabilityID")
    )
    non_critical_count = sum(
        1 for vulnerability in vulnerabilities if vulnerability.get("Severity") != "CRITICAL"
    )
    return ScanResult(len(vulnerabilities), non_critical_count, critical_ids)


def scan_image(image_ref: str, service: str, log_handle, log_path: Path, ignore_file: Path, vex_file: Path) -> ScanResult:
    argv = [
        *tool_command("trivy"),
        "image",
        "--scanners",
        "vuln",
        "--image-src",
        "remote",
        "--ignore-unfixed",
        "--severity",
        SCAN_SEVERITIES,
        "--format",
        "json",
        "--exit-code",
        "0",
        image_ref,
    ]
    result = subprocess.run(
        argv,
        check=False,
        text=True,
        capture_output=True,
    )
    log_handle.write(f"\n=== {service} ===\n")
    log_handle.write(f"image: {image_ref}\n")
    log_handle.write(f"severity threshold: {SCAN_SEVERITIES}\n")
    if ignore_file.exists():
        log_handle.write(f"local_ignore_file_not_applied: {ignore_file}\n")
    if vex_file.exists():
        log_handle.write(f"local_vex_file_not_applied: {vex_file}\n")
    log_handle.write(f"exit_code: {result.returncode}\n\n")
    if result.stdout:
        log_handle.write(result.stdout)
    if result.stderr:
        log_handle.write("\n--- stderr ---\n")
        log_handle.write(result.stderr)
    if not result.stdout and not result.stderr:
        log_handle.write("No output from trivy.\n")
    log_handle.write("\n")
    log_handle.flush()

    if result.returncode != 0:
        raise SystemExit(f"{service}: Trivy failed with exit code {result.returncode}; see {log_path}")
    scan_result = parse_trivy_result(result.stdout, service)
    if scan_result.finding_count == 0:
        print(f"[{service}] scan=PASS no fix-available {SCAN_SEVERITIES} vulnerabilities")
    else:
        print(f"[{service}] scan=FINDINGS count={scan_result.finding_count} see {log_path}")
    return scan_result


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
        "--validate-policy",
        action="store_true",
        help="Validate lock exception dates and local Critical acceptances without contacting registries",
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
    parser.add_argument(
        "--scan-log",
        type=Path,
        default=DEFAULT_SCAN_LOG,
        help=f"Write trivy scan output to this log file (default: {DEFAULT_SCAN_LOG.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--trivy-ignore-file",
        type=Path,
        default=DEFAULT_TRIVY_IGNORE_FILE,
        help=f"Optional local Trivy ignore file (default: {DEFAULT_TRIVY_IGNORE_FILE.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--trivy-vex-file",
        type=Path,
        default=DEFAULT_TRIVY_VEX_FILE,
        help=f"Optional local Trivy VEX file (default: {DEFAULT_TRIVY_VEX_FILE.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--critical-acceptance-file",
        type=Path,
        default=DEFAULT_CRITICAL_ACCEPTANCE_FILE,
        help=(
            "Optional untracked, digest- and CVE-specific Critical vulnerability acceptance file "
            f"(default: {DEFAULT_CRITICAL_ACCEPTANCE_FILE.relative_to(REPO_ROOT)})"
        ),
    )
    args = parser.parse_args()

    if args.check_tools:
        print_tool_status(skip_signature_verify=args.skip_signature_verify, skip_scan=args.skip_scan)
        return 0

    lock_data = load_lock_file(args.lock_file)
    images = lock_data["artifact_locked_images"]
    selected = args.service or list(images.keys())

    for service in selected:
        if service not in images:
            raise SystemExit(f"Unknown service in lock file: {service}")
        validate_exception_metadata(images[service], service)

    critical_acceptances = load_critical_acceptances(args.critical_acceptance_file)
    if args.validate_policy:
        print(f"Policy valid for {len(selected)} service(s); {len(critical_acceptances)} Critical acceptance(s) loaded")
        return 0

    for tool_name in required_tools(skip_signature_verify=args.skip_signature_verify, skip_scan=args.skip_scan):
        resolve_tool_command(tool_name)

    scan_failures: list[str] = []
    scan_log_handle = None
    if not args.skip_scan:
        args.scan_log.parent.mkdir(parents=True, exist_ok=True)
        scan_log_handle = args.scan_log.open("w", encoding="utf-8")
        scan_log_handle.write("# Container vulnerability scan findings\n")
        scan_log_handle.write(f"severity threshold: {SCAN_SEVERITIES}\n")
        scan_log_handle.write(f"lock file: {args.lock_file}\n")
        scan_log_handle.write(f"services: {', '.join(selected)}\n")

    try:
        for service in selected:
            entry = images[service]
            upstream_ref = entry["upstream_ref"]
            digest = resolve_digest(upstream_ref)
            print(f"[{service}] upstream={upstream_ref}")
            print(f"[{service}] digest={digest}")
            digest_ref = to_digest_ref(upstream_ref, digest)
            print(f"[{service}] approved={digest_ref}")

            current_digest = entry.get("approved_digest")
            if current_digest and digest != current_digest:
                created = inspect_image_created(upstream_ref)
                validate_minimum_image_age(created, service)
                print(f"[{service}] created={created.isoformat()} age=PASS")

            if args.registry:
                internal_ref = f"{args.registry}/{entry['internal_repo']}"
                print(f"[{service}] mirror={internal_ref}@{digest}")

            if entry.get("signature_required", False) and not args.skip_signature_verify:
                verify_signature(digest_ref, entry, service)

            scan_ok = True
            critical_no_regression = False
            if scan_log_handle is not None:
                scan_result = scan_image(
                    digest_ref,
                    service,
                    scan_log_handle,
                    args.scan_log,
                    args.trivy_ignore_file,
                    args.trivy_vex_file,
                )
                unaccepted_critical = sorted(
                    vulnerability_id
                    for vulnerability_id in scan_result.critical_ids
                    if (service, digest, vulnerability_id) not in critical_acceptances
                )
                if unaccepted_critical:
                    currently_approved_result = None
                    if current_digest and current_digest != digest:
                        current_ref = to_digest_ref(upstream_ref, current_digest)
                        currently_approved_result = scan_image(
                            current_ref,
                            f"{service} (currently approved)",
                            scan_log_handle,
                            args.scan_log,
                            args.trivy_ignore_file,
                            args.trivy_vex_file,
                        )
                    if critical_findings_are_preexisting(unaccepted_critical, currently_approved_result):
                        critical_no_regression = True
                        print(
                            f"[{service}] scan=NO-REGRESSION Critical findings are already "
                            "present in the currently approved image"
                        )
                    else:
                        print(
                            f"[{service}] scan=FAIL unaccepted Critical findings: "
                            f"{', '.join(unaccepted_critical)}"
                        )
                        scan_failures.append(service)
                        scan_ok = False
                if scan_ok and scan_result.non_critical_count:
                    if entry.get("vulnerability_exception") == NO_NEWER_IMAGE_EXCEPTION:
                        print(f"[{service}] scan=EXEMPT time-bounded non-Critical findings accepted")
                    else:
                        scan_failures.append(service)
                        scan_ok = False

            if not scan_ok:
                continue

            if args.registry:
                mirror_image(digest_ref, internal_ref, digest)

            if args.write:
                entry["approved_digest"] = digest
                if args.registry:
                    entry["notes"] = f"Approved via scripts/promote_artifacts.py and mirrored to {args.registry}"
                elif entry.get("vulnerability_exception") == NO_NEWER_IMAGE_EXCEPTION:
                    if critical_no_regression:
                        entry["notes"] = (
                            "Approved newer no-regression image via scripts/promote_artifacts.py; "
                            "Critical findings were also present in the previous digest and non-Critical "
                            f"findings are accepted through {entry['vulnerability_exception_expires_on']}."
                        )
                    else:
                        entry["notes"] = (
                            "Approved latest upstream image via scripts/promote_artifacts.py; "
                            f"non-Critical vulnerability findings accepted through "
                            f"{entry['vulnerability_exception_expires_on']}."
                        )
                elif critical_no_regression:
                    entry["notes"] = (
                        "Approved newer no-regression image via scripts/promote_artifacts.py; "
                        "Critical findings were also present in the previous digest."
                    )
                else:
                    entry["notes"] = "Approved via scripts/promote_artifacts.py"
    finally:
        if scan_log_handle is not None:
            scan_log_handle.close()

    if scan_failures:
        print(
            f"Vulnerability scan failed for {', '.join(scan_failures)}. "
            f"Review findings in {args.scan_log}."
        )
        return 1

    if args.write:
        with args.lock_file.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(lock_data, handle, sort_keys=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
