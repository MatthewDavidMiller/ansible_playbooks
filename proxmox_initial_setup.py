# Credits
# https://www.tutorialspoint.com/python/os_chmod.htm
# https://ochoaprojects.github.io/posts/ProxMoxCloudInitImage/

# Initial setup for proxmox.

# Vars
debianCloudURL = r"https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2"
debianCloudImageName = r"debian-12-genericcloud-amd64.qcow2"

import subprocess
import urllib.request

# update packages
subprocess.call([r"apt-get", r"update", r"-y"])
subprocess.call([r"apt-get", r"upgrade", r"-y"])

# Download Debian Cloud image
urllib.request.urlretrieve(
    debianCloudURL, r"/var/lib/vz/template/" + debianCloudImageName
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

# Setup disk for cloud init
subprocess.call([r"qm", r"set", r"400", r"--ide2", r"local-lvm:cloudinit"])

# Set boot to Disk image
subprocess.call([r"qm", r"set", r"400", r"--boot", r"c", r"--bootdisk", r"scsi0"])

# Set efi disk
subprocess.call(
    [
        r"qm",
        r"set",
        r"100",
        r"--efidisk0",
        r"local-lvm:1,format=raw,efitype=4m,pre-enrolled-keys=1",
    ]
)

# Add serial console
subprocess.call([r"qm", r"set", r"400", r"--serial0", r"socket", r"--vga", r"serial0"])

# Set bios for uefi
subprocess.call([r"qm", r"set", r"400", r"--bios", r"ovmf"])

# Set cores to 2
subprocess.call([r"qm", r"set", r"400", r"--cores", r"2"])

# Set memory to 2048 MB
subprocess.call([r"qm", r"set", r"400", r"--memory", r"2048"])

# Enable Qemu guest agent
subprocess.call([r"qm", r"set", r"400", r"--agent", r"enabled=1"])

# Configure VM as template
subprocess.call([r"qm", r"template", r"400"])

# Create Ansible VM
subprocess.call([r"qm", r"clone", r"400", r"100", r"--name", r"Ansible"])

# Set efi disk
subprocess.call(
    [
        r"qm",
        r"set",
        r"100",
        r"--efidisk0",
        r"local-lvm:1,format=raw,efitype=4m,pre-enrolled-keys=1",
    ]
)

# Create Nextcloud VM
subprocess.call([r"qm", r"clone", r"400", r"101", r"--name", r"Nextcloud"])

# Set efi disk
subprocess.call(
    [
        r"qm",
        r"set",
        r"101",
        r"--efidisk0",
        r"local-lvm:1,format=raw,efitype=4m,pre-enrolled-keys=1",
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
subprocess.call([r"qm", r"clone", r"400", r"103", r"--name", r"Pihole"])

# Set efi disk
subprocess.call(
    [
        r"qm",
        r"set",
        r"103",
        r"--efidisk0",
        r"local-lvm:1,format=raw,efitype=4m,pre-enrolled-keys=1",
    ]
)

# Create NetworkController VM
subprocess.call([r"qm", r"clone", r"400", r"104", r"--name", r"NetworkController"])

# Set efi disk
subprocess.call(
    [
        r"qm",
        r"set",
        r"104",
        r"--efidisk0",
        r"local-lvm:1,format=raw,efitype=4m,pre-enrolled-keys=1",
    ]
)

# Create VPN VM
subprocess.call([r"qm", r"clone", r"400", r"105", r"--name", r"VPN"])

# Set efi disk
subprocess.call(
    [
        r"qm",
        r"set",
        r"105",
        r"--efidisk0",
        r"local-lvm:1,format=raw,efitype=4m,pre-enrolled-keys=1",
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
