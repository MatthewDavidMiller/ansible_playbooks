from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
NEXTCLOUD_SCAN_HELPER = (
    REPO_ROOT / "roles" / "nextcloud" / "templates" / "nextcloud_scan_path.sh.j2"
)
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
        if "/usr/local/bin/nextcloud_scan_path.sh"
        in path.read_text(encoding="utf-8")
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
    file cache. The shared helper serializes the daily scans, waits through
    transient container failures, and recognizes errors that `occ files:scan`
    reports while still returning a successful process status.
    """

    def test_local_backups_use_the_managed_scan_helper(self):
        for template in local_nextcloud_backup_templates():
            with self.subTest(template=template.name):
                for command in joined_commands(template.read_text(encoding="utf-8")):
                    if "nextcloud_scan_path.sh" not in command:
                        continue
                    self.assertIn(
                        "/usr/local/bin/nextcloud_scan_path.sh",
                        command,
                        f"{template.name} must use the managed scan helper",
                    )
                occ_commands = [
                    command
                    for command in joined_commands(
                        template.read_text(encoding="utf-8")
                    )
                    if "podman exec" in command and "files:scan" in command
                ]
                self.assertFalse(
                    occ_commands,
                    f"{template.name} must not maintain a private occ scan invocation",
                )

    def test_scan_failures_are_reported_not_discarded(self):
        for template in local_nextcloud_backup_templates():
            with self.subTest(template=template.name):
                for command in joined_commands(template.read_text(encoding="utf-8")):
                    if "nextcloud_scan_path.sh" not in command:
                        continue
                    self.assertNotIn(
                        "|| true",
                        command,
                        f"{template.name} must not discard targeted scan failures",
                    )

    def test_scan_helper_handles_occ_semantic_and_transient_failures(self):
        helper = NEXTCLOUD_SCAN_HELPER.read_text(encoding="utf-8")
        self.assertIn("--user {{ nextcloud_uid }}:{{ nextcloud_gid }}", helper)
        self.assertIn("--workdir /var/www/html", helper)
        self.assertIn("php /var/www/html/occ files:scan", helper)
        self.assertIn("/usr/bin/flock --wait", helper)
        self.assertIn("max_attempts=", helper)
        self.assertIn("Unknown user", helper)
        self.assertIn("Another process is already scanning", helper)
        self.assertIn("Exception during scan", helper)

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


def role_tasks(role: str, tasks_file: str = "main.yml") -> list[dict]:
    return yaml.safe_load(
        (REPO_ROOT / "roles" / role / "tasks" / tasks_file).read_text(encoding="utf-8")
    )


def network_reconcile_calls(role: str) -> list[dict]:
    """Vars each `include_role: container_network` call in a role passes."""
    calls = []
    for task in role_tasks(role):
        include = task.get("ansible.builtin.include_role") or {}
        if include.get("name") == "container_network":
            calls.append(task.get("vars") or {})
    return calls


class SharedContainerNetworkTests(unittest.TestCase):
    """Guards for the single shared Podman network reconciliation path.

    This logic used to be copy-pasted into every service role, so a fix to the
    internal-flag or subnet-drift check reached only the role it was made in.
    Reconciliation now lives in `roles/container_network`, and the drift
    decision itself is the unit-tested `homelab_network_needs_replacement`
    filter rather than an inline Jinja expression.
    """

    #: Networks each role owns, and whether Podman must create them --internal.
    EXPECTED_NETWORKS = {
        "nextcloud": {"nextcloud_container_net": True, "nextcloud_proxy_net": True},
        "navidrome": {"navidrome_container_net": True},
        "paperless_ngx": {"paperless_proxy_net": True},
        "vaultwarden": {"vaultwarden_container_net": True},
        "semaphore": {
            "semaphore_container_net": True,
            "{{ semaphore_egress_network }}": False,
        },
        "reverse_proxy": {
            "{{ traefik_egress_network }}": False,
            "{{ route_proxy_network_name }}": True,
        },
    }

    def test_every_service_role_reconciles_the_networks_it_owns(self):
        for role, expected in self.EXPECTED_NETWORKS.items():
            with self.subTest(role=role):
                declared = {
                    call["container_network_name"]: call.get(
                        "container_network_internal", True
                    )
                    for call in network_reconcile_calls(role)
                }
                self.assertEqual(declared, expected)

    def test_no_role_reimplements_network_reconciliation(self):
        """A role that shells out to `podman network` has forked the logic."""
        for tasks in sorted(REPO_ROOT.glob("roles/*/tasks/*.yml")):
            if tasks.parents[1].name == "container_network":
                continue
            with self.subTest(tasks=str(tasks.relative_to(REPO_ROOT))):
                body = tasks.read_text(encoding="utf-8")
                self.assertNotIn("- network", body)
                self.assertNotIn("from_json", body)

    def test_service_networks_are_internal(self):
        """Only the two deliberate egress networks may reach the host network."""
        external = {
            (role, name)
            for role, networks in self.EXPECTED_NETWORKS.items()
            for name, internal in networks.items()
            if not internal
        }
        self.assertEqual(
            external,
            {
                ("semaphore", "{{ semaphore_egress_network }}"),
                ("reverse_proxy", "{{ traefik_egress_network }}"),
            },
        )

    def test_control_plane_networks_are_created_but_not_replaced_by_the_proxy(self):
        """Replacing semaphore_container_net from reverse_proxy would cut the
        Semaphore container running the playbook, so only the semaphore role
        may repair drift on it."""
        route_call = next(
            call
            for call in network_reconcile_calls("reverse_proxy")
            if call["container_network_name"] == "{{ route_proxy_network_name }}"
        )
        self.assertIn(
            "not in reverse_proxy_deferred_route_networks",
            route_call["container_network_reconcile_existing"],
        )
        defaults = role_defaults("reverse_proxy")
        self.assertIn(
            "semaphore_container_net", defaults["reverse_proxy_deferred_route_networks"]
        )

    def test_reconciliation_defers_replacement_during_staged_runs(self):
        defaults = role_defaults("container_network")
        self.assertIn(
            "apply_runtime_changes_on_reboot", defaults["container_network_defer"]
        )

        tasks = role_tasks("container_network")
        names = [task["name"] for task in tasks]
        queue = next(index for index, name in enumerate(names) if "Queue" in name)
        remove = next(index for index, name in enumerate(names) if "Remove" in name)
        create = next(index for index, name in enumerate(names) if "Create" in name)
        self.assertLess(queue, remove)
        self.assertLess(remove, create)

        # Removal and queueing are mutually exclusive: a staged run must never
        # tear a network down mid-play.
        self.assertIn("container_network_defer | bool", tasks[queue]["when"])
        self.assertIn("not (container_network_defer | bool)", tasks[remove]["when"])

    def test_drifted_networks_are_force_removed_before_recreation(self):
        remove = next(
            task
            for task in role_tasks("container_network")
            if task["name"].startswith("Remove drifted")
        )
        self.assertIn("--force", remove["ansible.builtin.command"]["argv"])


class ContainerNetworkMigrationTests(unittest.TestCase):
    def setUp(self):
        self.migration_role = REPO_ROOT / "roles" / "container_network_migration"
        self.script = (
            self.migration_role / "templates" / "migrate_container_networks.sh.j2"
        ).read_text(encoding="utf-8")

    def test_migration_is_coordinated_by_a_dedicated_final_role(self):
        playbook = yaml.safe_load((REPO_ROOT / "vm1.yml").read_text(encoding="utf-8"))
        roles = playbook[0]["roles"]

        self.assertGreater(
            roles.index("container_network_migration"), roles.index("semaphore")
        )
        self.assertGreater(
            roles.index("container_network_migration"), roles.index("standard_cleanup")
        )

        semaphore_tasks = (
            REPO_ROOT / "roles" / "semaphore" / "tasks" / "main.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Schedule deferred container network migration", semaphore_tasks)

    def test_migration_always_attempts_service_recovery(self):
        self.assertIn("trap finish EXIT", self.script)
        self.assertIn("restart_services", self.script)
        self.assertLess(
            self.script.index("trap finish EXIT"),
            self.script.index('echo "Stopping ${unit_name}"'),
        )

    def test_migration_does_not_discard_lifecycle_failures(self):
        for command in (
            "/usr/bin/systemctl stop",
            "/usr/bin/systemctl start",
            "/usr/bin/podman network rm",
        ):
            with self.subTest(command=command):
                matching_lines = [
                    line for line in self.script.splitlines() if command in line
                ]
                self.assertTrue(matching_lines)
                self.assertTrue(all("|| true" not in line for line in matching_lines))

    def test_migration_verifies_network_removal_and_creation(self):
        removal = self.script.index("/usr/bin/podman network rm")
        absence_check = self.script.index(
            "if ! /usr/bin/podman network inspect", removal
        )
        still_exists = self.script.index("still exists after removal")
        creation = self.script.index("/usr/bin/podman network create")
        not_created = self.script.index("was not created")

        self.assertLess(removal, absence_check)
        self.assertLess(absence_check, creation)
        self.assertLess(creation, still_exists)
        self.assertLess(creation, not_created)


if __name__ == "__main__":
    unittest.main()
