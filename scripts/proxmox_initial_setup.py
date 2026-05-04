#!/usr/bin/env python3
"""Initial Proxmox setup using a versioned, checksum-verified Rocky image."""

from __future__ import annotations

import hashlib
import re
import subprocess
import urllib.request
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
LOCK_FILE = REPO_ROOT / "artifacts" / "cloud_images.lock.yml"
DOWNLOAD_DIR = Path("/var/lib/vz/template")
ROCKY_TEMPLATE_ID = "401"
ROCKY_TEMPLATE_NAME = "RockyLinuxCloudInitTemplate"
VM_STORAGE = "local-lvm"

ROCKY_VMS = [
    {
        "vmid": "120",
        "name": "VM1",
        "cores": "2",
        "memory": "16384",
    },
    {
        "vmid": "121",
        "name": "VM2",
        "cores": "4",
        "memory": "32768",
        "root_disk_size": "100G",
    },
]


def run(argv: list[str]) -> None:
    subprocess.run(argv, check=True)


def capture(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, capture_output=True, text=True)


def qm_config(vmid: str) -> str | None:
    result = capture(["qm", "config", vmid])
    if result.returncode == 0:
        return result.stdout
    return None


def parse_qm_config(config: str) -> dict[str, str]:
    parsed = {}
    for line in config.splitlines():
        key, separator, value = line.partition(": ")
        if separator:
            parsed[key] = value
    return parsed


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


def load_rocky_image_lock() -> dict:
    with LOCK_FILE.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    image = data["cloud_image_lock"]["rocky_linux_10_x86_64"]
    for key in ("url", "filename", "sha256"):
        value = image[key]
        if value.startswith("REPLACE_WITH_"):
            raise SystemExit(
                f"{LOCK_FILE} still contains placeholder {key}; pin the official Rocky image first."
            )
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
    urllib.request.urlretrieve(url, partial)

    actual_sha256 = sha256sum(partial)
    if actual_sha256 != expected_sha256:
        partial.unlink(missing_ok=True)
        raise SystemExit(
            f"Checksum mismatch for {url}: expected {expected_sha256}, got {actual_sha256}"
        )

    partial.replace(destination)
    return destination


def create_rocky_template(image_path: Path) -> None:
    config = qm_config(ROCKY_TEMPLATE_ID)
    if config:
        parsed = parse_qm_config(config)
        if parsed.get("template") != "1":
            raise SystemExit(
                f"VMID {ROCKY_TEMPLATE_ID} already exists but is not a template."
            )
        configure_rocky_template()
        return

    run(
        [
            "qm",
            "create",
            ROCKY_TEMPLATE_ID,
            "--name",
            ROCKY_TEMPLATE_NAME,
            "--net0",
            "virtio,bridge=vmbr0",
        ]
    )
    run(["qm", "importdisk", ROCKY_TEMPLATE_ID, str(image_path), VM_STORAGE])
    run(
        [
            "qm",
            "set",
            ROCKY_TEMPLATE_ID,
            "--scsihw",
            "virtio-scsi-pci",
            "--scsi0",
            f"{VM_STORAGE}:vm-{ROCKY_TEMPLATE_ID}-disk-0",
        ]
    )
    run(["qm", "set", ROCKY_TEMPLATE_ID, "--scsi1", f"{VM_STORAGE}:cloudinit"])
    configure_rocky_template()
    run(["qm", "template", ROCKY_TEMPLATE_ID])


def configure_rocky_template() -> None:
    run(["qm", "set", ROCKY_TEMPLATE_ID, "--name", ROCKY_TEMPLATE_NAME])
    run(["qm", "set", ROCKY_TEMPLATE_ID, "--boot", "c", "--bootdisk", "scsi0"])
    run(["qm", "set", ROCKY_TEMPLATE_ID, "--serial0", "socket", "--vga", "serial0"])
    run(["qm", "set", ROCKY_TEMPLATE_ID, "--bios", "ovmf"])
    run(["qm", "set", ROCKY_TEMPLATE_ID, "--cores", "2"])
    run(["qm", "set", ROCKY_TEMPLATE_ID, "--memory", "2048"])
    run(["qm", "set", ROCKY_TEMPLATE_ID, "--agent", "enabled=1"])
    run(["qm", "set", ROCKY_TEMPLATE_ID, "--cpu", "host"])


def clone_rocky_vm(vm: dict[str, str]) -> None:
    vmid = vm["vmid"]
    config = qm_config(vmid)
    if config:
        parsed = parse_qm_config(config)
        if parsed.get("template") == "1":
            raise SystemExit(f"VMID {vmid} already exists as a template.")
    else:
        run(["qm", "clone", ROCKY_TEMPLATE_ID, vmid, "--name", vm["name"]])
        config = qm_config(vmid)
        if config is None:
            raise SystemExit(f"Unable to read config for cloned VMID {vmid}.")

    parsed = parse_qm_config(config)
    if "efidisk0" not in parsed:
        run(
            [
                "qm",
                "set",
                vmid,
                "--efidisk0",
                f"{VM_STORAGE}:1,format=raw,efitype=4m,pre-enrolled-keys=0",
            ]
        )

    run(["qm", "set", vmid, "--name", vm["name"]])
    run(["qm", "set", vmid, "--cores", vm["cores"]])
    run(["qm", "set", vmid, "--memory", vm["memory"]])

    root_disk_size = vm.get("root_disk_size")
    if root_disk_size:
        current_size = disk_size_bytes(config, "scsi0")
        target_size = parse_size_bytes(root_disk_size)
        if current_size is None or current_size < target_size:
            run(["qm", "resize", vmid, "scsi0", root_disk_size])


def main() -> int:
    rocky_image = load_rocky_image_lock()
    image_path = download_verified_image(
        rocky_image["url"],
        rocky_image["filename"],
        rocky_image["sha256"],
    )

    create_rocky_template(image_path)
    for vm in ROCKY_VMS:
        clone_rocky_vm(vm)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
