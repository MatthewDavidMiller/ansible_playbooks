#!/bin/bash

pacman -S --noconfirm --needed ansible

cat <<EOF >>"/etc/ansible/hosts"
[local]
localhost ansible_connection=local
EOF

systemctl start "dhcpcd.service"
ansible-galaxy collection install community.general
ansible-galaxy collection install community.crypto
