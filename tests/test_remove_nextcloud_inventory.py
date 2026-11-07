from pathlib import Path
import contextlib
import io
import stat
import sys
import tempfile
import unittest

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import remove_nextcloud_inventory as tool  # noqa: E402


# Made-up values only; this is a layout fixture, not anyone's inventory.
INVENTORY = """\
---
all:
  hosts:
    vm1:
      ansible_host: 192.0.2.10
      # The data disk
      nextcloud_disk: "UUID=0000-0000"
      nextcloud_disk_mount_path: /data_drive
      nextcloud_path: /data_drive/nextcloud
      nextcloud_borg_backup_path: /data_drive/nextcloud/borg_backup
      paperless_path: /paperless
      postgres_path: /postgres
      nextcloud_homelab_user: alice
      nextcloud_admin_password: !vault |
            $ANSIBLE_VAULT;1.1;AES256
            6162636465666768696a6b6c6d6e6f70
      nextcloud_db_user: nc
      paperless_secret_key: made-up
      postgres_admin_user: pg
      postgres_image: example/postgres@sha256:00
      password_minimum_length: 12
      backup_destination: homedrive
      backup_local: true
      borg_backup_hour: "3"
      nextcloud_webdav_path: https://example.invalid/dav
      nextcloud_rclone_pass: !vault |
            $ANSIBLE_VAULT;1.1;AES256
            7172737475767778797a303132333435
      homedrive_rclone_pass: kept
      music_server_path: /srv/music-server
      route_proxy_network_subnets:
        nextcloud_proxy_net: 172.16.1.32/29
        paperless_proxy_net: 172.16.1.40/29
        music_server_container_net: 172.16.1.48/29
      route_proxy_container_ips:
        nextcloud_proxy_net: 172.16.1.34
        paperless_proxy_net: 172.16.1.42
        music_server_container_net: 172.16.1.50
      route_proxy_traefik_ips:
        nextcloud_proxy_net: 172.16.1.35
        paperless_proxy_net: 172.16.1.43
      container_static_ips:
        postgres_backend: 172.16.1.2
        redis_backend: 172.16.1.3
        nextcloud_backend: 172.16.1.4
        paperless_backend: 172.16.1.5
        nextcloud_proxy: 172.16.1.34
        paperless_proxy: 172.16.1.42
        music_server_proxy: 172.16.1.50
      container_dns:
        domain: dns.podman
        aliases:
          postgres_backend: postgres-backend
          nextcloud_proxy: nextcloud-proxy
          paperless_proxy: paperless-proxy
          music_server_proxy: music-server-proxy
      proxy_config:
        - name: "nextcloud"
          proxy_fqdn: "nextcloud.example.lan"
          proxy_network: "nextcloud_proxy_net"

        - name: "paperless_ngx"
          proxy_fqdn: "paperless.example.lan"
          proxy_network: "paperless_proxy_net"

        - name: music_server_proxy
          proxy_fqdn: "music.example.lan"
          proxy_network: music_server_container_net
      container_service_names: "postgres_container redis_container nextcloud_container paperless_ngx vaultwarden music_server"
"""


class RemoveNextcloudInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "inventory.yml"
        self.path.write_text(INVENTORY, encoding="utf-8")
        self.path.chmod(0o640)

    def run_tool(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = tool.main([str(self.path), *args])
        return code, out.getvalue(), err.getvalue()

    def vm1(self):
        data = yaml.load(self.path.read_text(encoding="utf-8"), Loader=tool._Loader)
        return data["all"]["hosts"]["vm1"]

    def test_preview_changes_nothing_and_prints_no_values(self):
        code, out, _ = self.run_tool()
        self.assertEqual(code, 0)
        self.assertEqual(self.path.read_text(encoding="utf-8"), INVENTORY)
        self.assertIn("Preview only", out)
        for secret in ("ANSIBLE_VAULT", "UUID=0000", "alice", "made-up", "example.invalid"):
            self.assertNotIn(secret, out)

    def test_write_renames_removes_and_keeps_what_retirement_needs(self):
        code, out, err = self.run_tool("--write", "--no-backup")
        self.assertEqual(code, 0, out + err)
        vm1 = self.vm1()
        # Renamed in place, values untouched.
        self.assertEqual(vm1["data_disk"], "UUID=0000-0000")
        self.assertEqual(vm1["data_disk_mount_path"], "/data_drive")
        self.assertEqual(vm1["homedrive_main_user"], "alice")
        for old in ("nextcloud_disk", "nextcloud_disk_mount_path", "nextcloud_homelab_user"):
            self.assertNotIn(old, vm1)
        # Kept for retire_nextcloud.yml.
        for kept in ("nextcloud_path", "nextcloud_borg_backup_path", "paperless_path", "postgres_path"):
            self.assertIn(kept, vm1)
        # Removed.
        for gone in (
            "nextcloud_admin_password",
            "nextcloud_db_user",
            "paperless_secret_key",
            "postgres_admin_user",
            "postgres_image",
            "password_minimum_length",
            "backup_destination",
            "backup_local",
            "borg_backup_hour",
            "nextcloud_webdav_path",
            "nextcloud_rclone_pass",
        ):
            self.assertNotIn(gone, vm1)
        self.assertEqual(
            vm1["route_proxy_network_subnets"], {"music_server_container_net": "172.16.1.48/29"}
        )
        self.assertEqual(vm1["route_proxy_container_ips"], {"music_server_container_net": "172.16.1.50"})
        self.assertEqual(vm1["route_proxy_traefik_ips"], {})
        self.assertEqual(vm1["container_static_ips"], {"music_server_proxy": "172.16.1.50"})
        self.assertEqual(
            vm1["container_dns"]["aliases"], {"music_server_proxy": "music-server-proxy"}
        )
        self.assertEqual([r["name"] for r in vm1["proxy_config"]], ["music_server_proxy"])
        self.assertEqual(vm1["container_service_names"], "vaultwarden music_server")
        # Unrelated values are untouched, including a secret.
        self.assertEqual(vm1["homedrive_rclone_pass"], "kept")
        self.assertEqual(vm1["music_server_path"], "/srv/music-server")

    def test_all_flag_removes_the_retirement_paths_too(self):
        self.run_tool("--write", "--no-backup")
        code, out, _ = self.run_tool("--all", "--write", "--no-backup")
        self.assertEqual(code, 0, out)
        vm1 = self.vm1()
        for gone in ("nextcloud_path", "nextcloud_borg_backup_path", "paperless_path", "postgres_path"):
            self.assertNotIn(gone, vm1)
        self.assertIn("data_disk", vm1)

    def test_a_second_run_finds_nothing_to_do(self):
        self.run_tool("--all", "--write", "--no-backup")
        before = self.path.read_text(encoding="utf-8")
        code, out, _ = self.run_tool("--all", "--write", "--no-backup")
        self.assertEqual((code, out.strip()), (0, "Nothing to remove."))
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_backup_keeps_the_original_privately_and_the_mode_is_preserved(self):
        code, _, _ = self.run_tool("--write")
        self.assertEqual(code, 0)
        backups = list(Path(self.tmp.name).glob("inventory.yml.nextcloud-removal-*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), INVENTORY)
        self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o640)

    def test_it_will_not_rename_onto_a_name_already_in_the_file(self):
        text = INVENTORY.replace(
            "      music_server_path: /srv/music-server\n",
            "      music_server_path: /srv/music-server\n      homedrive_main_user: bob\n",
        )
        self.path.write_text(text, encoding="utf-8")
        code, _, err = self.run_tool("--write", "--no-backup")
        self.assertEqual(code, 1)
        self.assertIn("homedrive_main_user", err)
        self.assertEqual(self.path.read_text(encoding="utf-8"), text)

    def test_it_refuses_while_something_still_refers_to_a_renamed_or_removed_variable(self):
        for reference in ("{{ nextcloud_homelab_user }}", "{{ nextcloud_db_user }}"):
            with self.subTest(reference=reference):
                text = INVENTORY.replace(
                    "      music_server_path: /srv/music-server\n",
                    f'      music_server_path: /srv/music-server\n      homedrive_backup_user: "{reference}"\n',
                )
                self.path.write_text(text, encoding="utf-8")
                code, _, err = self.run_tool("--write", "--no-backup")
                self.assertEqual(code, 1)
                self.assertIn(reference.strip("{} "), err)
                self.assertEqual(self.path.read_text(encoding="utf-8"), text)


if __name__ == "__main__":
    unittest.main()
