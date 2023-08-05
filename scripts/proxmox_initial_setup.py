# Credits
# https://www.tutorialspoint.com/python/os_chmod.htm
# https://ochoaprojects.github.io/posts/ProxMoxCloudInitImage/

# Initial setup for proxmox.

# Vars
debianCloudURL = r"https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2"
debianCloudImageName = r"debian-12-genericcloud-amd64.qcow2"
archCloudURL = r"https://geo.mirror.pkgbuild.com/images/latest/Arch-Linux-x86_64-cloudimg.qcow2"
archCloudImageName = r"Arch-Linux-x86_64-cloudimg.qcow2"

import subprocess
import urllib.request

# update packages
subprocess.call([r"apt-get", r"update", r"-y"])
subprocess.call([r"apt-get", r"upgrade", r"-y"])

# Download Debian Cloud image
urllib.request.urlretrieve(
    debianCloudURL, r"/var/lib/vz/template/" + debianCloudImageName
)

# Download Arch Linux Cloud image
urllib.request.urlretrieve(
    archCloudURL, r"/var/lib/vz/template/" + archCloudImageName
)

# Create Debian Cloud Image Template
subprocess.call(
    [
        r"qm",
        r"create",
        r"400",
        r"--name",
        r"DebianCloudInitTemplate",
        r"--net0",
        r"virtio,bridge=vmbr0",
    ]
)


# Create Arch Linux Cloud Image Template
subprocess.call(
    [
        r"qm",
        r"create",
        r"401",
        r"--name",
        r"ArchCloudInitTemplate",
        r"--net0",
        r"virtio,bridge=vmbr0",
    ]
)

# Import disk image
subprocess.call(
    [
        r"qm",
        r"importdisk",
        r"400",
        r"/var/lib/vz/template/" + debianCloudImageName,
        r"local-lvm",
    ]
)

# Import disk image Arch
subprocess.call(
    [
        r"qm",
        r"importdisk",
        r"401",
        r"/var/lib/vz/template/" + archCloudImageName,
        r"local-lvm",
    ]
)

# Setup Disk
subprocess.call(
    [
        r"qm",
        r"set",
        r"400",
        r"--scsihw",
        r"virtio-scsi-pci",
        r"--scsi0",
        r"local-lvm:vm-400-disk-0",
    ]
)


# Setup Disk Arch
subprocess.call(
    [
        r"qm",
        r"set",
        r"401",
        r"--scsihw",
        r"virtio-scsi-pci",
        r"--scsi0",
        r"local-lvm:vm-401-disk-0",
    ]
)

# Setup disk for cloud init
subprocess.call([r"qm", r"set", r"400", r"--scsi1", r"local-lvm:cloudinit"])

# Setup disk for cloud init Arch
subprocess.call([r"qm", r"set", r"401", r"--scsi1", r"local-lvm:cloudinit"])

# Set boot to Disk image
subprocess.call([r"qm", r"set", r"400", r"--boot", r"c", r"--bootdisk", r"scsi0"])

# Set boot to Disk image Arch
subprocess.call([r"qm", r"set", r"401", r"--boot", r"c", r"--bootdisk", r"scsi0"])

# Add serial console
subprocess.call([r"qm", r"set", r"400", r"--serial0", r"socket", r"--vga", r"serial0"])

# Add serial console Arch
subprocess.call([r"qm", r"set", r"401", r"--serial0", r"socket", r"--vga", r"serial0"])

# Set bios for uefi
subprocess.call([r"qm", r"set", r"400", r"--bios", r"ovmf"])

# Set bios for uefi Arch
subprocess.call([r"qm", r"set", r"401", r"--bios", r"ovmf"])

# Set cores to 2
subprocess.call([r"qm", r"set", r"400", r"--cores", r"2"])

# Set cores to 2 Arch
subprocess.call([r"qm", r"set", r"401", r"--cores", r"2"])

# Set memory to 2048 MB
subprocess.call([r"qm", r"set", r"400", r"--memory", r"2048"])

# Set memory to 2048 MB Arch
subprocess.call([r"qm", r"set", r"401", r"--memory", r"2048"])

# Enable Qemu guest agent
subprocess.call([r"qm", r"set", r"400", r"--agent", r"enabled=1"])

# Enable Qemu guest agent Arch
subprocess.call([r"qm", r"set", r"401", r"--agent", r"enabled=1"])

# Configure VM as template
subprocess.call([r"qm", r"template", r"400"])

# Configure VM as template Arch
subprocess.call([r"qm", r"template", r"401"])

# Create Ansible VM
subprocess.call([r"qm", r"clone", r"401", r"100", r"--name", r"Ansible"])

# Set efi disk
subprocess.call(
    [
        r"qm",
        r"set",
        r"100",
        r"--efidisk0",
        r"local-lvm:1,format=raw,efitype=4m,pre-enrolled-keys=0",
    ]
)

# Create Nextcloud VM
subprocess.call([r"qm", r"clone", r"401", r"113", r"--name", r"Nextcloud"])

# Set efi disk
subprocess.call(
    [
        r"qm",
        r"set",
        r"113",
        r"--efidisk0",
        r"local-lvm:1,format=raw,efitype=4m,pre-enrolled-keys=0",
    ]
)

# Create Vaultwarden VM
subprocess.call([r"qm", r"clone", r"400", r"102", r"--name", r"Vaultwarden"])

# Set efi disk
subprocess.call(
    [
        r"qm",
        r"set",
        r"102",
        r"--efidisk0",
        r"local-lvm:1,format=raw,efitype=4m,pre-enrolled-keys=1",
    ]
)

# Create Pihole VM
subprocess.call([r"qm", r"clone", r"401", r"111", r"--name", r"Pihole"])

# Set efi disk
subprocess.call(
    [
        r"qm",
        r"set",
        r"111",
        r"--efidisk0",
        r"local-lvm:1,format=raw,efitype=4m,pre-enrolled-keys=0",
    ]
)

# Create NetworkController VM
subprocess.call([r"qm", r"clone", r"401", r"112", r"--name", r"NetworkController"])

# Set efi disk
subprocess.call(
    [
        r"qm",
        r"set",
        r"112",
        r"--efidisk0",
        r"local-lvm:1,format=raw,efitype=4m,pre-enrolled-keys=0",
    ]
)

# Create VPN VM
subprocess.call([r"qm", r"clone", r"401", r"110", r"--name", r"VPN"])

# Set efi disk
subprocess.call(
    [
        r"qm",
        r"set",
        r"110",
        r"--efidisk0",
        r"local-lvm:1,format=raw,efitype=4m,pre-enrolled-keys=0",
    ]
)

# Create Backup VM
subprocess.call([r"qm", r"clone", r"400", r"106", r"--name", r"Backup"])

# Set efi disk
subprocess.call(
    [
        r"qm",
        r"set",
        r"106",
        r"--efidisk0",
        r"local-lvm:1,format=raw,efitype=4m,pre-enrolled-keys=1",
    ]
)

# Create Navidrome VM
subprocess.call([r"qm", r"clone", r"401", r"114", r"--name", r"Navidrome"])

# Set efi disk
subprocess.call(
    [
        r"qm",
        r"set",
        r"114",
        r"--efidisk0",
        r"local-lvm:1,format=raw,efitype=4m,pre-enrolled-keys=0",
    ]
)
