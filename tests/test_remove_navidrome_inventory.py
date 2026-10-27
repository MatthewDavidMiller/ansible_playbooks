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

import remove_navidrome_inventory as tool  # noqa: E402


# Made-up values only; this is a layout fixture, not anyone's inventory. The
# variables sit under the vm1 host, quoted the way the routes usually are.
INVENTORY = """\
---
all:
  hosts:
    vm1:
      ansible_host: 192.0.2.10
      nextcloud_webdav_pass: !vault |
            $ANSIBLE_VAULT;1.1;AES256
            6162636465666768696a6b6c6d6e6f70
      # Navidrome
      navidrome_path: /srv/navidrome
      navidrome_local_music_path: /srv/nextcloud/data/admin/files/Music
      navidrome_backup_location: Nextcloud:navidrome_backup
      navidrome_uid: "33"
      navidrome_gid: "33"
      music_server_path: /srv/music-server
      route_proxy_network_subnets:
        nextcloud_proxy_net: 172.16.1.32/29
        navidrome_container_net: 172.16.1.24/29
        music_server_container_net: 172.16.1.48/29
      route_proxy_container_ips:
        navidrome_container_net: 172.16.1.26
        music_server_container_net: 172.16.1.50
      route_proxy_traefik_ips:
        navidrome_container_net: 172.16.1.27
      container_static_ips:
        postgres_backend: 172.16.1.2
        navidrome_proxy: 172.16.1.26
      container_dns:
        domain: dns.podman
        aliases:
          postgres_backend: postgres-backend
          navidrome_proxy: navidrome-proxy
          music_server_proxy: music-server-proxy
      proxy_config:
        - name: "nextcloud"
          proxy_fqdn: "nextcloud.example.lan"
          proxy_network: "nextcloud_proxy_net"

        - name: "navidrome"
          proxy_fqdn: "navidrome.example.lan"
          proxy_upstream_port: "4533"
          proxy_network: "navidrome_container_net"
          container_destination: "{{ container_dns.aliases.navidrome_proxy }}.{{ container_dns.domain }}"

        - name: music_server_proxy
          proxy_fqdn: "music.example.lan"
          proxy_network: music_server_container_net
      container_service_names: "postgres_container nextcloud_container paperless_ngx navidrome_container vaultwarden"
"""


class RemoveNavidromeInventoryTests(unittest.TestCase):
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
        self.assertNotIn("ANSIBLE_VAULT", out)
        self.assertNotIn("/srv/navidrome", out)

    def test_write_removes_everything_but_navidrome_path(self):
        code, out, err = self.run_tool("--write", "--no-backup")
        self.assertEqual(code, 0, out + err)
        vm1 = self.vm1()
        self.assertEqual(vm1["navidrome_path"], "/srv/navidrome")
        for gone in (
            "navidrome_local_music_path",
            "navidrome_backup_location",
            "navidrome_uid",
            "navidrome_gid",
        ):
            self.assertNotIn(gone, vm1)
        self.assertEqual(
            vm1["route_proxy_network_subnets"],
            {"nextcloud_proxy_net": "172.16.1.32/29", "music_server_container_net": "172.16.1.48/29"},
        )
        self.assertEqual(vm1["route_proxy_container_ips"], {"music_server_container_net": "172.16.1.50"})
        self.assertEqual(vm1["route_proxy_traefik_ips"], {})
        self.assertEqual(vm1["container_static_ips"], {"postgres_backend": "172.16.1.2"})
        self.assertEqual(
            vm1["container_dns"]["aliases"],
            {"postgres_backend": "postgres-backend", "music_server_proxy": "music-server-proxy"},
        )
        self.assertEqual([r["name"] for r in vm1["proxy_config"]], ["nextcloud", "music_server_proxy"])
        self.assertEqual(
            vm1["container_service_names"],
            "postgres_container nextcloud_container paperless_ngx vaultwarden",
        )
        # Unrelated secrets and values are untouched.
        self.assertIn("ANSIBLE_VAULT", self.path.read_text(encoding="utf-8"))
        self.assertEqual(vm1["music_server_path"], "/srv/music-server")

    def test_all_flag_removes_navidrome_path_too(self):
        self.run_tool("--write", "--no-backup")
        code, out, _ = self.run_tool("--all", "--write", "--no-backup")
        self.assertEqual(code, 0, out)
        self.assertNotIn("navidrome", self.path.read_text(encoding="utf-8").lower())

    def test_a_second_run_finds_nothing_to_do(self):
        self.run_tool("--all", "--write", "--no-backup")
        before = self.path.read_text(encoding="utf-8")
        code, out, _ = self.run_tool("--all", "--write", "--no-backup")
        self.assertEqual((code, out.strip()), (0, "Nothing to remove."))
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_backup_keeps_the_original_privately_and_the_mode_is_preserved(self):
        code, _, _ = self.run_tool("--write")
        self.assertEqual(code, 0)
        backups = list(Path(self.tmp.name).glob("inventory.yml.navidrome-removal-*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), INVENTORY)
        self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o640)

    def test_it_refuses_while_something_still_refers_to_a_removed_variable(self):
        text = INVENTORY.replace(
            "      music_server_path: /srv/music-server\n",
            '      music_server_path: /srv/music-server\n      music_server_music_path: "{{ navidrome_local_music_path }}"\n',
        )
        self.path.write_text(text, encoding="utf-8")
        code, _, err = self.run_tool("--write", "--no-backup")
        self.assertEqual(code, 1)
        self.assertIn("navidrome_local_music_path", err)
        self.assertEqual(self.path.read_text(encoding="utf-8"), text)


if __name__ == "__main__":
    unittest.main()
