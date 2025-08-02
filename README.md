# Ansible Playbooks

Collection of various Ansible playbooks to configure various Linux servers and services. Used on Arch Linux servers except the backup server which runs on Debian 12. Utilizes podman containers for most of the services.

## Playbooks

* [ansible.yml](ansible.yml): Configures a server running Semaphore
* [unificontroller.yml](unificontroller.yml): Configures a server running the Ubiquiti Unifi controller
* [backup.yml](backup.yml): Configures a server running borg backup that backs up a Nextcloud server
* [navidrome.yml](navidrome.yml): Configures a server running Navidrome
* [nextcloud.yml](nextcloud.yml): Configures a server running Nextcloud and paperless ngx
* [vaultwarden.yml](vaultwarden.yml): Configures a server running Vaultwarden
* [vpn.yml](vpn.yml): Configures a Wireguard VPN server
* [pihole.yml](pihole.yml): Configures a server running Phole

## Setup
Run playbooks on servers using Ansible

[proxmox_initial_setup.py](scripts/proxmox_initial_setup.py) Example Proxmox VM setup in this script

[example_inventory.yml](example_inventory.yml) Example inventory file with variables here

## License

Copyright (c) Matthew David Miller. All rights reserved.

[Licensed under the MIT License.](LICENSE)
