#!/usr/bin/env python3
"""Resolve, verify, scan, and optionally mirror approved container artifacts."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import functools
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
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
# Bounds a Critical acceptance in the untracked acceptance file. Time-bounded
# lock-file exceptions for non-Critical findings no longer exist: staying on an
# older image to avoid findings the newer one also has is not a trade worth
# making, so currency is the policy and findings are reported instead.
MAX_EXCEPTION_DAYS = 30
MINIMUM_IMAGE_AGE_HOURS = 24
SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
FALLBACK_TOOL_IMAGES = {
    "skopeo": "quay.io/skopeo/stable@sha256:abded792af33493f9aaa08132f564d3f9c12818193c0adc0a62f44ed84a04eda",
    "cosign": "ghcr.io/sigstore/cosign/cosign@sha256:6bbe0d281d955c79f85b325f0f7e651c1bcab5a4fa4ad4903d74955178a3b2eb",
    "trivy": "public.ecr.aws/aquasecurity/trivy@sha256:016eae51fdcf989332a5404af7e8f625cd5d95d7c0907a221d080a996f556500",
}
ANNOUNCED_FALLBACKS: set[str] = set()


@dataclass(frozen=True)
class ScanResult:
    finding_count: int
    non_critical_count: int
    critical_ids: frozenset[str]


@dataclass(frozen=True)
class ImageInspection:
    digest: str
    created: datetime | None


def run(argv: list[str], *, capture_output: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def container_engine() -> str | None:
    """Locate Podman, the only engine this repository's tooling runs on.

    Inside the toolbox this resolves to the podman-remote client, which runs
    the fallback container on the host engine through the mounted API socket.
    """
    return shutil.which("podman")


def trivy_cache_path() -> Path:
    """Where to keep trivy's vulnerability database between runs.

    The path has to name the same directory here and on the host, because the
    container is started by the host engine: inside the toolbox this script
    talks to it through podman-remote, so the engine resolves every bind mount
    in the host's filesystem rather than in ours. $HOME in the toolbox is
    /home/toolbox, which exists in the image and nowhere else, and asking the
    host to mount it fails the run outright with
    `statfs /home/toolbox/.cache/trivy: no such file or directory`.

    /tmp is bind-mounted at /tmp for exactly this reason, so a cache under it
    means the same thing on both sides. It matches the /tmp/ansible-playbooks-*
    convention the linters already use for their caches, and `make clean`
    removes it with them. On a host run the ordinary XDG location is right and
    keeps the database across reboots.
    """
    if os.environ.get("ANSIBLE_PLAYBOOKS_IN_TOOLBOX"):
        return Path("/tmp/ansible-playbooks-trivy-cache")
    return Path.home() / ".cache" / "trivy"


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


@functools.lru_cache(maxsize=None)
def resolve_tool_command(name: str) -> tuple[tuple[str, ...], str]:
    """Locate a tool, preferring a native binary over the pinned container.

    Cached because every service in a run needs the same three tools, and
    resolving one probes PATH, the container engine, and the credential
    helper config each time.
    """
    local_binary = shutil.which(name)
    if local_binary is not None:
        return (local_binary,), f"local binary ({local_binary})"

    engine = container_engine()
    if engine is None:
        raise SystemExit(
            f"Required tool not available: {name}. Install it locally or ensure podman is available "
            f"for the pinned container fallback. See {TOOLING_GUIDE}."
        )

    # trivy copies every file it analyses into a scratch directory, so its /tmp
    # has to fit the largest single file in the image being scanned rather than
    # anything about the image as a whole. Paperless ships PyTorch, and
    # libtorch_cpu.so on its own overruns a small tmpfs: the scan then dies
    # partway through a layer with "no space left on device", which reads as a
    # full disk rather than a container limit. skopeo and cosign only ever hold
    # a manifest or a signature, so they keep the small allowance.
    tmp_size = "4g" if name == "trivy" else "256m"
    argv = [
        engine,
        "run",
        "--rm",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--read-only",
        "--tmpfs",
        f"/tmp:rw,noexec,nosuid,nodev,size={tmp_size}",
    ]
    if name != "trivy":
        argv.extend(["--tmpfs", "/root/.cache:rw,noexec,nosuid,nodev,size=128m"])
    argv.extend(["--security-opt", "label=disable"])

    # Registry credentials, in the two formats the tools inside the container
    # read. The Docker config format is what skopeo and trivy look for; Podman
    # writes its own auth.json under ~/.config/containers.
    docker_config = Path.home() / ".docker" / "config.json"
    if not docker_config_uses_external_helpers(docker_config):
        add_mount(argv, Path.home() / ".docker", "/root/.docker")
    add_mount(argv, Path.home() / ".config" / "containers", "/root/.config/containers")

    if name == "trivy":
        trivy_cache_dir = trivy_cache_path()
        trivy_cache_dir.mkdir(parents=True, exist_ok=True)
        add_mount(argv, trivy_cache_dir, "/root/.cache/trivy", read_only=False)
        add_mount(argv, REPO_ROOT, str(REPO_ROOT))

    argv.append(FALLBACK_TOOL_IMAGES[name])
    return tuple(argv), f"container fallback via {engine} ({FALLBACK_TOOL_IMAGES[name]})"


def tool_command(name: str) -> list[str]:
    argv, description = resolve_tool_command(name)
    if description.startswith("container fallback") and name not in ANNOUNCED_FALLBACKS:
        ANNOUNCED_FALLBACKS.add(name)
        print(f"[{name}] using {description}", file=sys.stderr)
    return list(argv)


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
    if not isinstance(data, dict) or not isinstance(data.get("artifact_locked_images"), dict):
        raise SystemExit(f"Invalid lock file format: {path}")
    return data


def write_lock_file(path: Path, data: dict) -> None:
    """Atomically replace a validated artifact lock without changing its mode."""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            yaml.safe_dump(data, handle, sort_keys=False)
            handle.flush()
            os.fsync(handle.fileno())

        if path.exists():
            temporary_path.chmod(stat.S_IMODE(path.stat().st_mode))
        os.replace(temporary_path, path)
        temporary_path = None

        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except (Exception, KeyboardInterrupt, SystemExit):
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def validate_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_DIGEST.fullmatch(value):
        raise SystemExit(f"{label} must be a full lowercase sha256 digest")
    return value


def validate_lock_entry(entry: object, service: str) -> dict:
    if not isinstance(entry, dict):
        raise SystemExit(f"{service}: lock entry must be a mapping")
    for field in ("upstream_ref", "internal_repo"):
        if not isinstance(entry.get(field), str) or not entry[field].strip():
            raise SystemExit(f"{service}: {field} must be a non-empty string")
    if "approved_digest" in entry:
        validate_digest(entry["approved_digest"], f"{service}: approved_digest")
    if not isinstance(entry.get("signature_required", False), bool):
        raise SystemExit(f"{service}: signature_required must be a boolean")
    if entry.get("signature_required"):
        signature_verification_args(entry, service)
    return entry


def parse_policy_date(value: object, field: str, service: str) -> date:
    if not isinstance(value, str):
        raise SystemExit(f"{service}: {field} must be an ISO date (YYYY-MM-DD)")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"{service}: {field} must be an ISO date (YYYY-MM-DD)") from exc


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
        for field in ("service", "vulnerability_id", "reason"):
            if not isinstance(record[field], str) or not record[field].strip():
                raise SystemExit(f"{label}: {field} must be a non-empty string")
        digest = validate_digest(record["image_digest"], f"{label}: image_digest")
        accepted.add((str(record["service"]), digest, str(record["vulnerability_id"])))
    return accepted


def inspect_image(upstream_ref: str) -> ImageInspection:
    result = run([*tool_command("skopeo"), "inspect", f"docker://{upstream_ref}"])
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Failed to inspect image metadata for {upstream_ref}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Failed to inspect image metadata for {upstream_ref}")

    digest = validate_digest(data.get("Digest"), f"{upstream_ref}: resolved digest")
    created_value = data.get("Created")
    if created_value is None:
        created = None
    else:
        try:
            created = datetime.fromisoformat(str(created_value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise SystemExit(f"Failed to read image creation time for {upstream_ref}") from exc
        if created.tzinfo is None:
            raise SystemExit(f"Image creation time for {upstream_ref} has no timezone")
        created = created.astimezone(timezone.utc)
    return ImageInspection(digest=digest, created=created)


def resolve_digest(upstream_ref: str) -> str:
    return inspect_image(upstream_ref).digest


def inspect_image_created(upstream_ref: str) -> datetime:
    created = inspect_image(upstream_ref).created
    if created is None:
        raise SystemExit(f"Failed to read image creation time for {upstream_ref}")
    return created


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


def parse_version_tag(tag: object) -> tuple[str, tuple[int, ...]] | None:
    """Split a release tag into its optional prefix and numeric components.

    Returns None for anything that is not purely a dotted number with an
    optional single-letter prefix, which is what keeps `latest`, `stable`,
    `17-bookworm` and `3.0.5-rc1` out of the candidate set.
    """
    if not isinstance(tag, str):
        return None
    match = re.fullmatch(r"(?P<prefix>[A-Za-z]*)(?P<version>\d+(?:\.\d+)*)", tag.strip())
    if match is None:
        return None
    return match.group("prefix"), tuple(int(part) for part in match.group("version").split("."))


def list_upstream_tags(repository: str) -> list[str]:
    result = run([*tool_command("skopeo"), "list-tags", f"docker://{repository}"])
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Failed to list tags for {repository}") from exc
    tags = data.get("Tags") if isinstance(data, dict) else None
    if not isinstance(tags, list):
        raise SystemExit(f"Failed to list tags for {repository}")
    return [tag for tag in tags if isinstance(tag, str)]


@dataclass(frozen=True)
class TagSelection:
    tag: str
    is_newer: bool
    held_back: tuple[str, ...]


def select_newest_tag(current_tag: object, tags: list[str]) -> TagSelection | None:
    """Pick the newest release of the same major line as the current tag.

    A newer image is worth having on its own: upstream fixes bugs that never
    become CVEs, so refusing to move because the scanner still reports
    something leaves the deployment on strictly older code. Currency is
    therefore the default, and only two things hold it back -- the minimum age
    gate applied by the caller, and a major version boundary, because a major
    is where upstream is allowed to break the configuration this repository
    renders.

    Candidates must share the current tag's exact shape: the same prefix and
    the same number of components. Registries carry `17.11` beside `17.11.0`
    and `v3.7.13` beside `3.7.13`, and mixing those spellings would make the
    selected tag depend on which variant a registry happens to publish.
    """
    current = parse_version_tag(current_tag)
    if current is None:
        return None
    prefix, current_version = current

    same_line: list[tuple[tuple[int, ...], str]] = []
    newer_major: list[tuple[tuple[int, ...], str]] = []
    for tag in tags:
        parsed = parse_version_tag(tag)
        if parsed is None:
            continue
        tag_prefix, version = parsed
        if tag_prefix != prefix or len(version) != len(current_version):
            continue
        if version[0] == current_version[0]:
            same_line.append((version, tag))
        elif version > current_version:
            newer_major.append((version, tag))

    if not same_line:
        return None

    best_version, best_tag = max(same_line)
    # Reported rather than selected, so a major bump stays a decision someone
    # makes and tests instead of one a scheduled review makes for them.
    held_back = tuple(tag for _, tag in sorted(newer_major)[-3:])
    return TagSelection(
        tag=best_tag,
        is_newer=best_version > current_version,
        held_back=held_back,
    )


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
    if not isinstance(report, dict) or not isinstance(report.get("Results", []), list):
        raise SystemExit(f"{service}: Trivy returned an invalid report structure")
    vulnerabilities = []
    for result in report.get("Results", []):
        if not isinstance(result, dict):
            raise SystemExit(f"{service}: Trivy returned an invalid report structure")
        result_vulnerabilities = result.get("Vulnerabilities")
        if result_vulnerabilities is None:
            result_vulnerabilities = []
        if not isinstance(result_vulnerabilities, list) or not all(
            isinstance(vulnerability, dict) for vulnerability in result_vulnerabilities
        ):
            raise SystemExit(f"{service}: Trivy returned an invalid report structure")
        vulnerabilities.extend(result_vulnerabilities)
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
    parser.add_argument("--write", action="store_true", help="Write updated tags and digests back to the lock file")
    parser.add_argument(
        "--keep-pinned-tag",
        action="store_true",
        help=(
            "Review the tag already in the lock file instead of selecting the newest "
            "release of the same major line"
        ),
    )
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
        validate_lock_entry(images[service], service)

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
            repository = upstream_ref.rsplit(":", 1)[0] if ":" in upstream_ref.rsplit("/", 1)[-1] else upstream_ref
            selected_tag = entry.get("approved_tag")

            # Move to the newest release of the same major line before anything
            # else looks at the image, so the rest of the run judges the version
            # this repository should be running rather than the one it happens
            # to be pinned to.
            if not args.keep_pinned_tag:
                selection = select_newest_tag(entry.get("approved_tag"), list_upstream_tags(repository))
                if selection is None:
                    print(f"[{service}] tag={entry.get('approved_tag')} (not a release version; left pinned)")
                else:
                    selected_tag = selection.tag
                    if selection.is_newer:
                        print(f"[{service}] tag={entry.get('approved_tag')} -> {selected_tag}")
                    if selection.held_back:
                        print(
                            f"[{service}] held-back={', '.join(selection.held_back)} "
                            "(new major; promote by hand after checking the config it renders)"
                        )
                upstream_ref = f"{repository}:{selected_tag}"

            inspection = inspect_image(upstream_ref)
            digest = inspection.digest
            print(f"[{service}] upstream={upstream_ref}")
            print(f"[{service}] digest={digest}")
            digest_ref = to_digest_ref(upstream_ref, digest)
            print(f"[{service}] approved={digest_ref}")

            current_digest = entry.get("approved_digest")
            if current_digest and digest != current_digest:
                created = inspection.created
                if created is None:
                    raise SystemExit(f"Failed to read image creation time for {upstream_ref}")
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
                # Findings do not block a promotion on their own. Refusing to
                # move while upstream has published something newer keeps the
                # deployment on older code carrying the same findings plus every
                # bug fixed since, which is strictly worse. What still blocks is
                # a regression: a Critical this image introduces that the digest
                # it would replace did not have.
                if unaccepted_critical:
                    if not current_digest or current_digest == digest:
                        # Already on this digest, so there is nothing newer to
                        # move to and nothing to have regressed from. Standing
                        # findings are reported, loudly, and reviewed by hand.
                        print(
                            f"[{service}] scan=STANDING Critical findings on the approved image, "
                            f"no newer release available: {', '.join(unaccepted_critical)}"
                        )
                    else:
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
                            introduced = sorted(
                                set(unaccepted_critical) - currently_approved_result.critical_ids
                            )
                            print(
                                f"[{service}] scan=FAIL Critical findings introduced by this image: "
                                f"{', '.join(introduced)}"
                            )
                            scan_failures.append(service)
                            scan_ok = False
                if scan_ok and scan_result.non_critical_count:
                    print(
                        f"[{service}] scan=REPORTED {scan_result.non_critical_count} "
                        "non-Critical finding(s); see the scan log"
                    )

            if not scan_ok:
                continue

            if args.registry:
                mirror_image(digest_ref, internal_ref, digest)

            if args.write:
                entry["upstream_ref"] = upstream_ref
                entry["approved_tag"] = selected_tag
                entry["approved_digest"] = digest
                if args.registry:
                    entry["notes"] = f"Approved via scripts/promote_artifacts.py and mirrored to {args.registry}"
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
        write_lock_file(args.lock_file, lock_data)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
