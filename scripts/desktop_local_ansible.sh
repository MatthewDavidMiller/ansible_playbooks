#!/bin/bash

set -euo pipefail

pacman -S --noconfirm --needed ansible

cat <<EOF >>"/etc/ansible/hosts"
[local]
localhost ansible_connection=local
EOF

systemctl start "dhcpcd.service"
ansible-galaxy collection install -r collections/requirements.yml -p ./collections
