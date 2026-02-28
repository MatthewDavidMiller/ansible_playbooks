# Laptop Roles Reference

These roles configure an Arch Linux laptop. They are grouped into three stages: Stage 1 install, Stage 2 install, and post-install configuration.

See [playbooks.md](../playbooks.md) for the playbooks that compose these roles.

---

## Stage 1 Install Roles

Run from `laptop_arch_install_1.yml` against a live Arch ISO environment. Partition and install the base system.

### `setup_efi_partition`

Creates and formats the EFI system partition (FAT32).

---

### `setup_lvm_encrypted_partition`

Sets up a LUKS2 encrypted container on the main partition.

---

### `setup_lvm`

Creates an LVM volume group and logical volumes inside the LUKS container.

---

### `setup_filesystems`

Formats logical volumes with ext4.

---

### `initial_install_mount_filesystems`

Mounts root and EFI partitions in preparation for `pacstrap`.

---

### `initial_Arch_install`

Installs the Arch Linux base system, kernel, and firmware via `pacstrap`.

---

## Stage 2 Install Roles

Run from `laptop_arch_install_2.yml` inside the installed system (chrooted or booted into the new system).

### `configure_hosts`

Writes `/etc/hosts` with localhost and hostname entries.

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `hosts.j2` | `/etc/hosts` | hosts file |

---

### `configure_hostname`

Writes the system hostname to `/etc/hostname`.

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `hostname.j2` | `/etc/hostname` | hostname file |

---

### `configure_locales`

Sets locale (used in both install stages and laptop config).

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `locale.j2` | `/etc/locale.conf` | locale configuration |

---

### `install_packages_extra`

Installs additional packages needed for the configured system (beyond base install).

---

### `get_uuids`

Gathers block device UUIDs. Output is used by `setup_fstab`.

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `uuids.j2` | — | Stores gathered UUIDs for fstab generation |

---

### `setup_fstab`

Writes `/etc/fstab` using UUIDs gathered by `get_uuids`.

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `fstab.j2` | `/etc/fstab` | Filesystem table |

---

### `enable_swap`

Enables the swap logical volume.

---

### `configure_kernel`

Sets kernel parameters (e.g., microcode, initramfs hooks for LUKS/LVM).

---

### `setup_systemd_boot`

Configures systemd-boot as the bootloader. Writes the loader config and Arch Linux boot entry.

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `loader.j2` | `/boot/loader/loader.conf` | systemd-boot loader config |
| `arch_linux.j2` | `/boot/loader/entries/arch.conf` | Boot entry for Arch Linux |

---

### `enable_network_manager`

Enables NetworkManager for post-install network connectivity.

---

### `enable_ntpd`

Enables NTP time synchronization.

---

### `create_groups`

Creates system groups (e.g., `wheel`, `video`).

---

### `create_users`

Creates the primary user account.

---

### `configure_sudo`

Configures sudoers (allows `wheel` group, disables lecture, sets secure path). Used in both install stage 2 and laptop config.

---

### `lock_root`

Locks the root account password.

---

## Configuration Roles

Run from `laptop_config.yml` on an already-installed Arch Linux system.

### `multilib_config`

Enables the `[multilib]` repository in `pacman.conf` for 32-bit package support.

---

### `install_packages_univ`

Installs the universal package set (common tools, fonts, utilities).

---

### `enable_firewalld`

Enables the firewalld service.

---

### `enable_apparmor`

Enables AppArmor mandatory access control.

---

### `default_firewalld_config`

Applies default firewalld rules for a laptop (trusts the local network, restricts incoming).

---

### `configure_wm`

Configures the Sway window manager. Writes the Sway config and autostart script.

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `sway.j2` | `~/.config/sway/config` | Sway configuration |
| `sway_autostart.j2` | `~/.config/sway/autostart` | Autostart script |

---

### `configure_aliases`

Writes shell aliases to the user's profile.

---

### `user_profile_path`

Adds directories to the user's `$PATH`.

---

### `configure_git`

Configures git user name, email, and SSH signing key.

---

### `configure_psd`

Configures profile-sync-daemon to cache browser profiles in tmpfs.

---

### `aur_builds`

Builds and installs AUR packages using paru.

**Templates (build scripts):**

| Template | Package |
|---|---|
| `paru.j2` | paru (AUR helper) |
| `powershell_aur.j2` | PowerShell |
| `rpi_imager_aur.j2` | Raspberry Pi Imager |
| `spotify_aur.j2` | Spotify |
| `vscode_aur.j2` | Visual Studio Code |

---

### `enable_bluetooth`

Enables the bluetooth service.

---

### `enable_paccache`

Enables the paccache timer to clean the pacman package cache weekly.

---

### `pacman_hooks_directory`

Creates `/etc/pacman.d/hooks/` for custom pacman hooks.

---

### `fwupd_config`

Configures fwupd for firmware updates.

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `fwupd.j2` | `/etc/fwupd/daemon.conf` | fwupd daemon config |

---

### `reflector_config`

Configures reflector to rank Arch mirrors by speed.

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `reflector.j2` | `/etc/xdg/reflector/reflector.conf` | reflector configuration |

---

### `enable_cups`

Enables the CUPS printing service.

---

### `configure_virt_manager`

Configures virt-manager and libvirt for virtual machine management.

---

### `configure_terminal`

Configures the terminal emulator settings.

---

### `user_autologin`

Configures automatic login on the primary TTY via a getty override.

**Templates:**

| Template | Destination | Description |
|---|---|---|
| `getty_override.j2` | `/etc/systemd/system/getty@tty1.service.d/override.conf` | Getty autologin override |

---

### `configure_firejail`

Sets up firejail application sandboxing profiles.

---

### `configure_scripts`

Copies utility scripts to the user's PATH.

**Templates:**

| Template | Description |
|---|---|
| `backup_env.j2` | Environment backup script |
| `build_openwrt_image.j2` | OpenWrt image build script |

---

### `configure_home_folder`

Creates standard home directory structure (e.g., `~/Documents`, `~/Projects`).

---

### `install_packages_extra`

Installs extra packages beyond the universal set. See [Stage 2 install](#install_packages_extra).
