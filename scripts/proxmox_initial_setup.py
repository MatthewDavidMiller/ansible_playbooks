# Credits
# https://www.tutorialspoint.com/python/os_chmod.htm
# https://ochoaprojects.github.io/posts/ProxMoxCloudInitImage/

# Initial setup for proxmox.

# Vars
rockyCloudURL = r"https://dl.rockylinux.org/pub/rocky/10/images/x86_64/Rocky-10-GenericCloud-Base.latest.x86_64.qcow2"
rockyCloudImageName = r"Rocky-10-GenericCloud-Base.latest.x86_64.qcow2"

import subprocess
import urllib.request

# update packages
subprocess.call([r"apt-get", r"update", r"-y"])
subprocess.call([r"apt-get", r"upgrade", r"-y"])

# Download Rocky Linux Cloud image
urllib.request.urlretrieve(
    rockyCloudURL, r"/var/lib/vz/template/" + rockyCloudImageName
)

# Create Rocky Linux Cloud Image Template
subprocess.call(
    [
        r"qm",
        r"create",
        r"401",
        r"--name",
        r"RockyLinuxCloudInitTemplate",
        r"--net0",
        r"virtio,bridge=vmbr0",
    ]
)

# Import disk image Rocky Linux
subprocess.call(
    [
        r"qm",
        r"importdisk",
        r"401",
        r"/var/lib/vz/template/" + rockyCloudImageName,
        r"local-lvm",
    ]
)

# Setup Disk Rocky Linux
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

# Setup disk for cloud init Rocky Linux
subprocess.call([r"qm", r"set", r"401", r"--scsi1", r"local-lvm:cloudinit"])

# Set boot to Disk image Rocky Linux
subprocess.call([r"qm", r"set", r"401", r"--boot", r"c", r"--bootdisk", r"scsi0"])

# Add serial console Rocky Linux
subprocess.call([r"qm", r"set", r"401", r"--serial0", r"socket", r"--vga", r"serial0"])

# Set bios for uefi Rocky Linux
subprocess.call([r"qm", r"set", r"401", r"--bios", r"ovmf"])

# Set cores to 2 Rocky Linux
subprocess.call([r"qm", r"set", r"401", r"--cores", r"2"])

# Set memory to 2048 MB Rocky Linux
subprocess.call([r"qm", r"set", r"401", r"--memory", r"2048"])

# Enable Qemu guest agent Rocky Linux
subprocess.call([r"qm", r"set", r"401", r"--agent", r"enabled=1"])

# Set CPU type to host for Rocky Linux (required to prevent kernel panic on boot)
subprocess.call([r"qm", r"set", r"401", r"--cpu", r"host"])

# Configure VM as template Rocky Linux
subprocess.call([r"qm", r"template", r"401"])

# Create VM1
subprocess.call([r"qm", r"clone", r"401", r"120", r"--name", r"VM1"])
subprocess.call([r"qm", r"set", r"120", r"--efidisk0",
    r"local-lvm:1,format=raw,efitype=4m,pre-enrolled-keys=0"])
subprocess.call([r"qm", r"set", r"120", r"--cores", r"4"])
subprocess.call([r"qm", r"set", r"120", r"--memory", r"8192"])
