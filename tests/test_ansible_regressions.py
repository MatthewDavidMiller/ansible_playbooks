from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from filter_plugins.homelab_validation import homelab_container_assignable_ip  # noqa: E402


SERVICE_NETWORK_CLAIM = re.compile(
    r"--network=(?P<network>[A-Za-z0-9_.-]+):ip=\{\{ container_static_ips\.(?P<alias>\w+) \}\}"
)


def role_defaults(role: str) -> dict:
    return yaml.safe_load(
        (REPO_ROOT / "roles" / role / "defaults" / "main.yml").read_text(encoding="utf-8")
    )


def service_route_claims() -> dict[str, dict[str, str]]:
    """Static addresses service launch scripts request, keyed by network then role."""
    claims: dict[str, dict[str, str]] = {}
    for template in sorted(REPO_ROOT.glob("roles/*/templates/*.sh.j2")):
        role = template.parents[1].name
        static_ips = role_defaults(role).get("container_static_ips") or {}
        for match in SERVICE_NETWORK_CLAIM.finditer(template.read_text(encoding="utf-8")):
            address = static_ips.get(match["alias"])
            if address is None:
                raise AssertionError(
                    f"{template.name} requests container_static_ips.{match['alias']}, "
                    f"which the {role} role does not define"
                )
            claims.setdefault(match["network"], {})[role] = address
    if not claims:
        raise AssertionError("no service launch script requests a static address")
    return claims


def local_nextcloud_backup_templates() -> list[Path]:
    """Templates whose backups are installed into the Nextcloud user files tree."""
    templates = [
        path
        for path in sorted(REPO_ROOT.glob("roles/*/templates/*.j2"))
        if "files:scan" in path.read_text(encoding="utf-8")
    ]
    if not templates:
        raise AssertionError("no local Nextcloud backup templates found")
    return templates


def joined_commands(script: str) -> list[str]:
    """Collapse backslash line continuations so each command is one string."""
    return script.replace("\\\n", " ").splitlines()


class LocalNextcloudBackupTests(unittest.TestCase):
    """Guards for backups written straight into the Nextcloud data directory.

    A file placed there is invisible to Nextcloud until it is scanned into the
    file cache. `occ` refuses to run as root, so a scan issued without --user
    fails; when that failure is also discarded the backup silently never
    appears, and only the next playbook run reconciles the tree.
    """

    def test_scan_runs_as_the_nextcloud_file_owner(self):
        for template in local_nextcloud_backup_templates():
            with self.subTest(template=template.name):
                for command in joined_commands(template.read_text(encoding="utf-8")):
                    if "php occ" not in command:
                        continue
                    self.assertIn(
                        "--user {{ nextcloud_uid }}:{{ nextcloud_gid }}",
                        command,
                        f"{template.name} must run occ as the config.php owner",
                    )

    def test_scan_failures_are_reported_not_discarded(self):
        for template in local_nextcloud_backup_templates():
            with self.subTest(template=template.name):
                for command in joined_commands(template.read_text(encoding="utf-8")):
                    if "files:scan" not in command:
                        continue
                    self.assertNotIn(
                        "|| true",
                        command,
                        f"{template.name} must not discard occ files:scan failures",
                    )

    def test_backups_are_installed_with_the_normalized_file_mode(self):
        """The nextcloud role rewrites file modes under data/<user>/files.

        Hard-coding a different mode here means every backup sits wrong until
        the next playbook run silently corrects it.
        """
        for template in local_nextcloud_backup_templates():
            with self.subTest(template=template.name):
                installs = [
                    command
                    for command in joined_commands(template.read_text(encoding="utf-8"))
                    if "install" in command and '"$DEST/"' in command
                ]
                self.assertTrue(installs, f"{template.name} installs no backup file")
                for command in installs:
                    self.assertIn("nextcloud_user_files_file_mode", command)

    def test_normalized_file_mode_default_matches_the_backup_templates(self):
        defaults = yaml.safe_load(
            (REPO_ROOT / "roles" / "nextcloud" / "defaults" / "main.yml").read_text(
                encoding="utf-8"
            )
        )
        role_mode = defaults["nextcloud_user_files_file_mode"]
        for template in local_nextcloud_backup_templates():
            with self.subTest(template=template.name):
                self.assertIn(
                    f"nextcloud_user_files_file_mode | default('{role_mode}')",
                    template.read_text(encoding="utf-8"),
                    f"{template.name} fallback mode must match the nextcloud role",
                )

    def test_backup_destinations_are_not_recursively_chmodded(self):
        """A recursive mode on the destination also rewrites the backup files."""
        for role in ("navidrome", "vaultwarden", "semaphore"):
            tasks = yaml.safe_load(
                (REPO_ROOT / "roles" / role / "tasks" / "main.yml").read_text(
                    encoding="utf-8"
                )
            )
            for task in tasks:
                options = task.get("ansible.builtin.file") or {}
                if not options.get("recurse"):
                    continue
                with self.subTest(role=role, task=task.get("name")):
                    self.assertNotIn("mode", options)


class RouteProxyAddressTests(unittest.TestCase):
    """Guards for address assignment on the internal route proxy networks.

    Podman gives a container that requests no address the first free address in
    the subnet, which is the address the service container asks for by name. A
    Traefik left to IPAM therefore takes it first and the service dies with
    "IPAM error: requested ip address ... is already allocated".
    """

    def setUp(self):
        self.defaults = role_defaults("reverse_proxy")
        self.subnets = self.defaults["route_proxy_network_subnets"]
        self.traefik_ips = self.defaults["route_proxy_traefik_ips"]
        self.backend_ips = self.defaults["route_proxy_container_ips"]
        self.claims = service_route_claims()

    def test_traefik_requests_an_address_on_every_route_proxy_network(self):
        template = (
            REPO_ROOT / "roles" / "reverse_proxy" / "templates" / "traefik_container.sh.j2"
        ).read_text(encoding="utf-8")
        self.assertIn("ip={{ route_proxy_traefik_ips[net] }}", template)
        for network in self.subnets:
            with self.subTest(network=network):
                self.assertIn(network, self.traefik_ips)

    def test_traefik_and_service_addresses_never_collide(self):
        for network, service_addresses in self.claims.items():
            if network not in self.traefik_ips:
                continue
            requested = dict(service_addresses, traefik=self.traefik_ips[network])
            with self.subTest(network=network):
                self.assertEqual(
                    len(set(requested.values())),
                    len(requested),
                    f"containers on {network} request the same address: {requested}",
                )

    def test_every_route_proxy_address_is_assignable_in_its_subnet(self):
        for network, subnet in self.subnets.items():
            addresses = dict(self.claims.get(network, {}))
            addresses["traefik"] = self.traefik_ips[network]
            addresses["traefik_hosts_entry"] = self.backend_ips[network]
            for owner, address in addresses.items():
                with self.subTest(network=network, owner=owner):
                    self.assertTrue(
                        homelab_container_assignable_ip(address, subnet),
                        f"{address} is not an address Podman can assign in {subnet}",
                    )

    def test_traefik_hosts_entries_match_the_service_addresses(self):
        for network, service_addresses in self.claims.items():
            if network not in self.backend_ips:
                continue
            with self.subTest(network=network):
                self.assertIn(self.backend_ips[network], service_addresses.values())


class AnsibleRegressionTests(unittest.TestCase):
    def test_container_runtime_harness_falls_back_to_podman(self):
        script = (REPO_ROOT / "scripts" / "test_container_security.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("command -v docker", script)
        self.assertIn("command -v podman", script)
        self.assertIn("DOCKER=podman", script)

    def test_nextcloud_permission_normalization_uses_one_idempotent_walk(self):
        tasks = yaml.safe_load(
            (REPO_ROOT / "roles" / "nextcloud" / "tasks" / "main.yml").read_text(
                encoding="utf-8"
            )
        )
        matching = [
            task for task in tasks
            if task.get("name") == "Normalize Nextcloud user file tree permissions"
        ]
        self.assertEqual(len(matching), 1)
        argv = matching[0]["ansible.builtin.command"]["argv"]
        self.assertEqual(argv.count("find"), 1)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child_directory = root / "directory"
            child_file = child_directory / "file"
            child_directory.mkdir(mode=0o700)
            child_file.write_text("content", encoding="utf-8")
            child_file.chmod(0o600)
            rendered = [
                str(root) if value == "{{ item }}" else
                "0770" if value == "{{ nextcloud_user_files_directory_mode }}" else
                "0660" if value == "{{ nextcloud_user_files_file_mode }}" else
                value
                for value in argv
            ]
            first = subprocess.run(rendered, check=True, capture_output=True, text=True)
            second = subprocess.run(rendered, check=True, capture_output=True, text=True)
            directory_mode = child_directory.stat().st_mode & 0o777
            file_mode = child_file.stat().st_mode & 0o777

        self.assertTrue(first.stdout)
        self.assertEqual(second.stdout, "")
        self.assertEqual(directory_mode, 0o770)
        self.assertEqual(file_mode, 0o660)


if __name__ == "__main__":
    unittest.main()
