#!/usr/bin/env python3
"""Initial Proxmox setup using a versioned, checksum-verified Rocky image."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
LOCK_FILE_ENV = "PROXMOX_CLOUD_IMAGE_LOCK"
DEFAULT_LOCK_FILE = REPO_ROOT / "artifacts" / "cloud_images.lock.yml"
DOWNLOAD_DIR = Path("/var/lib/vz/template")
ROCKY_TEMPLATE_ID = "401"
ROCKY_TEMPLATE_NAME = "RockyLinuxCloudInitTemplate"
VM_STORAGE = "local-lvm"
DOWNLOAD_TIMEOUT = 60
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

ROCKY_VMS = [
    {
        "vmid": "120",
        "name": "VM1",
        "cores": "2",
        "memory": "16384",
    },
]


def run(argv: list[str]) -> None:
    subprocess.run(argv, check=True)


def run_change(message: str, argv: list[str]) -> None:
    run(argv)
    print(f"CHANGE: {message}", flush=True)


def capture(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, capture_output=True, text=True)


def qm_config(vmid: str) -> str | None:
    result = capture(["qm", "config", vmid])
    if result.returncode == 0:
        return result.stdout

    error = (result.stderr or result.stdout).strip()
    normalized_error = error.casefold()
    if (
        "does not exist" in normalized_error
        or (
            "configuration file" in normalized_error
            and "not found" in normalized_error
        )
    ):
        return None
    raise SystemExit(
        f"Unable to query Proxmox config for VMID {vmid}: "
        f"{error or f'qm exited with status {result.returncode}'}"
    )


def parse_qm_config(config: str) -> dict[str, str]:
    parsed = {}
    for line in config.splitlines():
        key, separator, value = line.partition(": ")
        if separator:
            parsed[key] = value
    return parsed


def require_managed_identity(
    parsed: dict[str, str],
    vmid: str,
    expected_name: str,
    expected_type: str,
) -> None:
    actual_name = parsed.get("name")
    if actual_name != expected_name:
        raise SystemExit(
            f"VMID {vmid} is not the managed {expected_type}: expected name "
            f"{expected_name!r}, found {actual_name!r}. Refusing to modify it."
        )


def parse_size_bytes(size: str) -> int:
    match = re.fullmatch(r"(?P<value>\d+(?:\.\d+)?)(?P<unit>[KMGTP]?)", size)
    if not match:
        raise ValueError(f"Unsupported Proxmox size value: {size}")

    units = {
        "": 1,
        "K": 1024,
        "M": 1024**2,
        "G": 1024**3,
        "T": 1024**4,
        "P": 1024**5,
    }
    return int(float(match.group("value")) * units[match.group("unit")])


def disk_size_bytes(config: str, disk: str) -> int | None:
    parsed = parse_qm_config(config)
    disk_config = parsed.get(disk, "")
    match = re.search(r"(?:^|,)size=([^,]+)", disk_config)
    if not match:
        return None
    return parse_size_bytes(match.group(1))


def set_vm_options(
    vmid: str,
    parsed: dict[str, str],
    options: dict[str, str],
    message: str,
) -> None:
    changes = {key: value for key, value in options.items() if parsed.get(key) != value}
    if not changes:
        return

    argv = ["qm", "set", vmid]
    for key, value in changes.items():
        argv.extend([f"--{key}", value])

    details = ", ".join(f"{key}={value}" for key, value in changes.items())
    run_change(f"{message}: {details}", argv)
    parsed.update(changes)


def resolve_lock_file() -> Path:
    configured = os.environ.get(LOCK_FILE_ENV)
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            DEFAULT_LOCK_FILE,
            Path.cwd() / "artifacts" / "cloud_images.lock.yml",
        ]
    )

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    checked = "\n".join(f"  - {candidate}" for candidate in candidates)
    raise SystemExit(
        "Unable to find the Rocky cloud image lock file.\n"
        f"Checked:\n{checked}\n"
        "Run this script from the repository root, copy artifacts/cloud_images.lock.yml "
        f"alongside the repository layout, or set {LOCK_FILE_ENV}=/path/to/cloud_images.lock.yml."
    )


def load_rocky_image_lock() -> dict:
    lock_file = resolve_lock_file()
    with lock_file.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    try:
        image = data["cloud_image_lock"]["rocky_linux_10_x86_64"]
    except (KeyError, TypeError) as exc:
        raise SystemExit(f"Invalid Rocky cloud image lock format: {lock_file}") from exc
    if not isinstance(image, dict):
        raise SystemExit(f"Invalid Rocky cloud image lock format: {lock_file}")
    for key in ("url", "filename", "sha256"):
        value = image.get(key)
        if not isinstance(value, str) or not value:
            raise SystemExit(f"{lock_file}: {key} must be a non-empty string")
        if value.startswith("REPLACE_WITH_"):
            raise SystemExit(
                f"{lock_file} still contains placeholder {key}; pin the official Rocky image first."
            )
    parsed_url = urlsplit(image["url"])
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise SystemExit(f"{lock_file}: Rocky cloud image URL must use HTTPS")
    filename = image["filename"]
    if Path(filename).name != filename or filename in {".", ".."}:
        raise SystemExit(f"{lock_file}: filename must be a safe basename")
    if not SHA256_HEX.fullmatch(image["sha256"]):
        raise SystemExit(f"{lock_file}: sha256 must contain exactly 64 lowercase hexadecimal characters")
    return image


def sha256sum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_verified_image(url: str, filename: str, expected_sha256: str) -> Path:
    destination = DOWNLOAD_DIR / filename
    if destination.exists() and sha256sum(destination) == expected_sha256:
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as response:
            with partial.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
    except (Exception, KeyboardInterrupt):
        partial.unlink(missing_ok=True)
        raise

    try:
        actual_sha256 = sha256sum(partial)
        if actual_sha256 != expected_sha256:
            raise SystemExit(
                f"Checksum mismatch for {url}: expected {expected_sha256}, got {actual_sha256}"
            )
        partial.replace(destination)
    except (Exception, KeyboardInterrupt, SystemExit):
        partial.unlink(missing_ok=True)
        raise

    print(f"CHANGE: Download cloud image {url} to {destination}", flush=True)
    return destination


def create_rocky_template() -> None:
    config = qm_config(ROCKY_TEMPLATE_ID)
    if config:
        parsed = parse_qm_config(config)
        if parsed.get("template") != "1":
            raise SystemExit(
                f"VMID {ROCKY_TEMPLATE_ID} already exists but is not a template."
            )
        require_managed_identity(
            parsed,
            ROCKY_TEMPLATE_ID,
            ROCKY_TEMPLATE_NAME,
            "Rocky template",
        )
        configure_rocky_template(parsed)
        return

    rocky_image = load_rocky_image_lock()
    image_path = download_verified_image(
        rocky_image["url"],
        rocky_image["filename"],
        rocky_image["sha256"],
    )

    run_change(
        f"Create Rocky template VMID {ROCKY_TEMPLATE_ID}",
        [
            "qm",
            "create",
            ROCKY_TEMPLATE_ID,
            "--name",
            ROCKY_TEMPLATE_NAME,
            "--net0",
            "virtio,bridge=vmbr0",
        ],
    )
    run_change(
        f"Import Rocky cloud image into VMID {ROCKY_TEMPLATE_ID}",
        ["qm", "importdisk", ROCKY_TEMPLATE_ID, str(image_path), VM_STORAGE],
    )
    run_change(
        f"Attach imported disk to VMID {ROCKY_TEMPLATE_ID}",
        [
            "qm",
            "set",
            ROCKY_TEMPLATE_ID,
            "--scsihw",
            "virtio-scsi-pci",
            "--scsi0",
            f"{VM_STORAGE}:vm-{ROCKY_TEMPLATE_ID}-disk-0",
        ],
    )
    run_change(
        f"Attach cloud-init disk to VMID {ROCKY_TEMPLATE_ID}",
        ["qm", "set", ROCKY_TEMPLATE_ID, "--scsi1", f"{VM_STORAGE}:cloudinit"],
    )
    configured_template = qm_config(ROCKY_TEMPLATE_ID)
    if configured_template is None:
        raise SystemExit(f"Unable to read config for template VMID {ROCKY_TEMPLATE_ID}.")
    parsed = parse_qm_config(configured_template)
    require_managed_identity(
        parsed,
        ROCKY_TEMPLATE_ID,
        ROCKY_TEMPLATE_NAME,
        "Rocky template",
    )
    configure_rocky_template(parsed)
    run_change(
        f"Mark VMID {ROCKY_TEMPLATE_ID} as a template",
        ["qm", "template", ROCKY_TEMPLATE_ID],
    )


def configure_rocky_template(parsed: dict[str, str]) -> None:
    set_vm_options(
        ROCKY_TEMPLATE_ID,
        parsed,
        {
            "name": ROCKY_TEMPLATE_NAME,
            "boot": "c",
            "bootdisk": "scsi0",
            "serial0": "socket",
            "vga": "serial0",
            "bios": "ovmf",
            "cores": "2",
            "memory": "2048",
            "agent": "enabled=1",
            "cpu": "host",
        },
        f"Configure Rocky template VMID {ROCKY_TEMPLATE_ID}",
    )


def clone_rocky_vm(vm: dict[str, str]) -> None:
    vmid = vm["vmid"]
    config = qm_config(vmid)
    if config:
        parsed = parse_qm_config(config)
        if parsed.get("template") == "1":
            raise SystemExit(f"VMID {vmid} already exists as a template.")
        require_managed_identity(parsed, vmid, vm["name"], "VM")
    else:
        run_change(
            f"Clone Rocky template VMID {ROCKY_TEMPLATE_ID} to VMID {vmid}",
            ["qm", "clone", ROCKY_TEMPLATE_ID, vmid, "--name", vm["name"]],
        )
        config = qm_config(vmid)
        if config is None:
            raise SystemExit(f"Unable to read config for cloned VMID {vmid}.")

    parsed = parse_qm_config(config)
    require_managed_identity(parsed, vmid, vm["name"], "VM")
    if "efidisk0" not in parsed:
        run_change(
            f"Add EFI disk to VMID {vmid}",
            [
                "qm",
                "set",
                vmid,
                "--efidisk0",
                f"{VM_STORAGE}:1,format=raw,efitype=4m,pre-enrolled-keys=0",
            ],
        )

    set_vm_options(
        vmid,
        parsed,
        {
            "name": vm["name"],
            "cores": vm["cores"],
            "memory": vm["memory"],
        },
        f"Configure VMID {vmid}",
    )

    root_disk_size = vm.get("root_disk_size")
    if root_disk_size:
        current_size = disk_size_bytes(config, "scsi0")
        target_size = parse_size_bytes(root_disk_size)
        if current_size is None or current_size < target_size:
            run_change(
                f"Resize VMID {vmid} scsi0 to {root_disk_size}",
                ["qm", "resize", vmid, "scsi0", root_disk_size],
            )


def main() -> int:
    create_rocky_template()
    for vm in ROCKY_VMS:
        clone_rocky_vm(vm)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
