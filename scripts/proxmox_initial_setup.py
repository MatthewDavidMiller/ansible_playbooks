#!/usr/bin/env python3
"""Initial Proxmox setup using a versioned, checksum-verified Rocky image."""

from __future__ import annotations

import hashlib
import subprocess
import urllib.request
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
LOCK_FILE = REPO_ROOT / "artifacts" / "cloud_images.lock.yml"
DOWNLOAD_DIR = Path("/var/lib/vz/template")


def run(argv: list[str]) -> None:
    subprocess.run(argv, check=True)


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


def main() -> int:
    rocky_image = load_rocky_image_lock()
    image_path = download_verified_image(
        rocky_image["url"],
        rocky_image["filename"],
        rocky_image["sha256"],
    )

    run(["qm", "create", "401", "--name", "RockyLinuxCloudInitTemplate", "--net0", "virtio,bridge=vmbr0"])
    run(["qm", "importdisk", "401", str(image_path), "local-lvm"])
    run(["qm", "set", "401", "--scsihw", "virtio-scsi-pci", "--scsi0", "local-lvm:vm-401-disk-0"])
    run(["qm", "set", "401", "--scsi1", "local-lvm:cloudinit"])
    run(["qm", "set", "401", "--boot", "c", "--bootdisk", "scsi0"])
    run(["qm", "set", "401", "--serial0", "socket", "--vga", "serial0"])
    run(["qm", "set", "401", "--bios", "ovmf"])
    run(["qm", "set", "401", "--cores", "2"])
    run(["qm", "set", "401", "--memory", "2048"])
    run(["qm", "set", "401", "--agent", "enabled=1"])
    run(["qm", "set", "401", "--cpu", "host"])
    run(["qm", "template", "401"])

    run(["qm", "clone", "401", "120", "--name", "VM1"])
    run(["qm", "set", "120", "--efidisk0", "local-lvm:1,format=raw,efitype=4m,pre-enrolled-keys=0"])
    run(["qm", "set", "120", "--cores", "4"])
    run(["qm", "set", "120", "--memory", "16384"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
