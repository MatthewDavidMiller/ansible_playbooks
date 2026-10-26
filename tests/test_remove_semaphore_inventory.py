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

import remove_semaphore_inventory as tool  # noqa: E402


# Made-up values only; this is a layout fixture, not anyone's inventory.
INVENTORY = """\
---
all:
  hosts:
    vm1:
      ansible_host: 192.0.2.10
  vars:
    postgres_admin_user: admin_user
    # Semaphore
    semaphore_database_name: sem_db
    semaphore_db_user: sem_user
    semaphore_db_password: !vault |
          $ANSIBLE_VAULT;1.1;AES256
          6162636465666768696a6b6c6d6e6f70
          7172737475767778797a303132333435
    semaphore_admin_name: admin
    semaphore_admin_email: admin@example.com
    semaphore_admin_password: plain-example-password
    semaphore_encryption_key: "0123456789abcdef0123456789abcdef"
    semaphore_known_hosts: |
      192.0.2.10 ssh-ed25519 AAAAexample
      # semaphore_proxy: this is data, not a key
    semaphore_backup_location: Nextcloud:semaphore_backup
    semaphore_egress_network: semaphore_egress_net
    semaphore_postgres_path: /srv/old-semaphore-postgres
    paperless_db_user: pl_user
    route_proxy_network_subnets:
      nextcloud_proxy_net: 172.16.1.32/29
      semaphore_container_net: 172.16.1.48/29
      playbook_runner_container_net: 172.16.1.56/29
    route_proxy_container_ips:
      semaphore_container_net: 172.16.1.50
      playbook_runner_container_net: 172.16.1.58
    route_proxy_traefik_ips:
      semaphore_container_net: 172.16.1.51
      playbook_runner_container_net: 172.16.1.59
    container_static_ips:
      postgres_backend: 172.16.1.2
      semaphore_backend: 172.16.1.6
      semaphore_proxy: 172.16.1.50
    container_dns:
      domain: dns.podman
      aliases:
        postgres_backend: postgres-backend
        semaphore_backend: semaphore-backend
        semaphore_proxy: semaphore-proxy
        semaphore_egress: semaphore-egress
        playbook_runner_proxy: playbook-runner-proxy
    reverse_proxy_deferred_route_networks:
      - semaphore_container_net
      - playbook_runner_container_net
    proxy_config:
      - name: nextcloud_proxy
        proxy_fqdn: cloud.example.com
        proxy_network: nextcloud_proxy_net
      # Semaphore
      - name: semaphore_proxy
        proxy_fqdn: semaphore.example.com
        container_destination: "{{ container_dns.aliases.semaphore_proxy }}.{{ container_dns.domain }}"
        proxy_network: semaphore_container_net
      # Runner
      - name: playbook_runner_proxy
        proxy_fqdn: runner.example.com
        proxy_network: playbook_runner_container_net
    container_service_names: "postgres_container nextcloud_container semaphore playbook_runner" # order
"""


class RemoveSemaphoreInventoryTests(unittest.TestCase):
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

    def load(self):
        return yaml.load(self.path.read_text(encoding="utf-8"), Loader=tool._Loader)

    def test_preview_changes_nothing_and_prints_no_values(self):
        code, out, _ = self.run_tool()
        self.assertEqual(code, 0)
        self.assertEqual(self.path.read_text(encoding="utf-8"), INVENTORY)
        self.assertIn("Preview only", out)
        for secret in ("plain-example-password", "0123456789abcdef", "ANSIBLE_VAULT", "AAAAexample"):
            self.assertNotIn(secret, out)

    def test_write_removes_everything_but_the_cleanup_variables(self):
        code, out, _ = self.run_tool("--write", "--no-backup")
        self.assertEqual(code, 0, out)
        text = self.path.read_text(encoding="utf-8")
        variables = self.load()["all"]["vars"]

        self.assertEqual(variables["semaphore_database_name"], "sem_db")
        self.assertEqual(variables["semaphore_db_user"], "sem_user")
        for gone in (
            "semaphore_db_password",
            "semaphore_admin_name",
            "semaphore_admin_email",
            "semaphore_admin_password",
            "semaphore_encryption_key",
            "semaphore_known_hosts",
            "semaphore_backup_location",
            "semaphore_egress_network",
            "semaphore_postgres_path",
        ):
            self.assertNotIn(gone, variables)
        self.assertEqual(
            variables["route_proxy_network_subnets"],
            {"nextcloud_proxy_net": "172.16.1.32/29", "playbook_runner_container_net": "172.16.1.56/29"},
        )
        self.assertEqual(
            variables["route_proxy_container_ips"], {"playbook_runner_container_net": "172.16.1.58"}
        )
        self.assertEqual(variables["container_static_ips"], {"postgres_backend": "172.16.1.2"})
        self.assertEqual(
            variables["container_dns"]["aliases"],
            {"postgres_backend": "postgres-backend", "playbook_runner_proxy": "playbook-runner-proxy"},
        )
        self.assertEqual(
            variables["reverse_proxy_deferred_route_networks"], ["playbook_runner_container_net"]
        )
        self.assertEqual(
            [route["name"] for route in variables["proxy_config"]],
            ["nextcloud_proxy", "playbook_runner_proxy"],
        )
        self.assertEqual(
            variables["container_service_names"],
            "postgres_container nextcloud_container playbook_runner",
        )
        # Everything else, including its comments, is left as it was.
        self.assertIn("    # Runner\n", text)
        self.assertIn("# order", text)
        # The label above the kept variables stays; the one above the route goes.
        self.assertEqual(text.count("# Semaphore"), 1)
        self.assertEqual(variables["paperless_db_user"], "pl_user")

    def test_all_flag_removes_the_cleanup_variables_too(self):
        self.run_tool("--write", "--no-backup")
        code, _, _ = self.run_tool("--all", "--write", "--no-backup")
        self.assertEqual(code, 0)
        variables = self.load()["all"]["vars"]
        self.assertNotIn("semaphore_database_name", variables)
        self.assertNotIn("semaphore_db_user", variables)
        self.assertNotIn("semaphore", self.path.read_text(encoding="utf-8").lower())

    def test_a_second_run_finds_nothing_to_do(self):
        self.run_tool("--all", "--write", "--no-backup")
        before = self.path.read_text(encoding="utf-8")
        code, out, _ = self.run_tool("--all", "--write", "--no-backup")
        self.assertEqual((code, out.strip()), (0, "Nothing to remove."))
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_backup_keeps_the_original_privately_and_the_mode_is_preserved(self):
        code, out, _ = self.run_tool("--write")
        self.assertEqual(code, 0)
        backups = list(Path(self.tmp.name).glob("inventory.yml.semaphore-removal-*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), INVENTORY)
        self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o640)
        self.assertNotIn("plain-example-password", out)
        self.assertEqual(
            sorted(p.name for p in Path(self.tmp.name).iterdir() if p.name.startswith(".")), []
        )

    def test_it_refuses_while_something_still_refers_to_a_removed_variable(self):
        text = INVENTORY.replace(
            "    paperless_db_user: pl_user\n",
            '    paperless_db_user: pl_user\n    playbook_runner_known_hosts: "{{ semaphore_known_hosts }}"\n',
        )
        self.path.write_text(text, encoding="utf-8")
        code, out, err = self.run_tool("--write", "--no-backup")
        self.assertEqual(code, 1)
        self.assertIn("semaphore_known_hosts", err)
        self.assertEqual(self.path.read_text(encoding="utf-8"), text)

    def test_it_refuses_a_layout_it_cannot_check(self):
        text = INVENTORY.replace(
            "    container_static_ips:\n      postgres_backend: 172.16.1.2\n      semaphore_backend: 172.16.1.6\n      semaphore_proxy: 172.16.1.50\n",
            "    container_static_ips: {postgres_backend: 172.16.1.2, semaphore_backend: 172.16.1.6}\n",
        )
        self.path.write_text(text, encoding="utf-8")
        code, _, err = self.run_tool("--write", "--no-backup")
        self.assertEqual(code, 1)
        self.assertIn("does not match", err)
        self.assertEqual(self.path.read_text(encoding="utf-8"), text)

    def test_it_refuses_a_file_that_is_not_valid_yaml(self):
        self.path.write_text("all: [unclosed\n", encoding="utf-8")
        code, _, err = self.run_tool("--write")
        self.assertEqual(code, 1)
        self.assertIn("not valid YAML", err)

    def test_emptied_collections_stay_valid_yaml(self):
        text = (
            "all:\n  vars:\n    reverse_proxy_deferred_route_networks:\n"
            "      - semaphore_container_net\n    proxy_config:\n"
            "      - name: s\n        proxy_network: semaphore_container_net\n"
            "    container_service_names: semaphore\n    other: 1\n"
        )
        self.path.write_text(text, encoding="utf-8")
        code, out, err = self.run_tool("--write", "--no-backup")
        self.assertEqual(code, 0, out + err)
        variables = self.load()["all"]["vars"]
        self.assertEqual(variables["reverse_proxy_deferred_route_networks"], [])
        self.assertEqual(variables["proxy_config"], [])
        self.assertEqual(variables["container_service_names"], "")
        self.assertEqual(variables["other"], 1)

    def test_a_route_that_only_mentions_semaphore_is_flagged_not_removed(self):
        text = INVENTORY.replace(
            "      # Runner\n",
            "      - name: monitor\n        proxy_fqdn: semaphore-status.example.com\n"
            "        proxy_network: nextcloud_proxy_net\n      # Runner\n",
        )
        self.path.write_text(text, encoding="utf-8")
        code, out, _ = self.run_tool("--write", "--no-backup")
        self.assertEqual(code, 2)
        self.assertIn("Check by hand", out)
        self.assertIn("name: monitor", self.path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
