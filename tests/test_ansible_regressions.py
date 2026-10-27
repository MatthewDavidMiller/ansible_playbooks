from pathlib import Path
import ipaddress
import re
import shlex
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


def restorecon_commands(tasks: list[dict]) -> list[str]:
    """Every restorecon invocation in a task file, each as one string."""
    commands = []
    for task in tasks:
        for module in ("ansible.builtin.command", "ansible.builtin.shell"):
            invocation = task.get(module)
            if isinstance(invocation, str):
                commands.append(invocation)
            elif isinstance(invocation, dict):
                argv = invocation.get("argv") or []
                commands.append(" ".join(argv) or invocation.get("cmd", ""))
    return [
        command
        for command in commands
        if re.search(r"(?<![\w./-])restorecon(?=\s)", command)
    ]


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
        self.assertIn("nextcloud php /var/www/html/occ", helper)
        self.assertIn('occ files:scan --path="$scan_path"', helper)
        self.assertIn("/usr/bin/flock --wait", helper)
        self.assertIn("max_attempts=", helper)
        self.assertIn("Unknown user", helper)
        self.assertIn("Another process is already scanning", helper)
        self.assertIn("Exception during scan", helper)
        self.assertIn("maintenance: true", helper)

    def test_scan_helper_fails_on_per_file_scan_errors(self):
        """`Error during scan` skips one file and still exits zero.

        That is how a backup goes unindexed while the cron job reports
        success, so both the message and the summary Errors column have to
        fail the scan.
        """
        helper = NEXTCLOUD_SCAN_HELPER.read_text(encoding="utf-8")
        self.assertIn("Error during scan", helper)
        self.assertIn("scan_error_count", helper)
        self.assertIn('[ "$scan_errors" -eq 0 ]', helper)

    def test_scan_helper_runs_under_a_cron_environment(self):
        """cron supplies almost no environment and no controlling terminal.

        Anything the scan needs has to be set here, every command has to be
        absolute so a different PATH cannot select another binary, and a hung
        occ has to be killed instead of holding the shared lock all night.
        """
        helper = NEXTCLOUD_SCAN_HELPER.read_text(encoding="utf-8")
        self.assertIn("export PATH=", helper)
        self.assertIn('export HOME="${HOME:-/root}"', helper)
        self.assertIn("export LC_ALL=", helper)
        self.assertIn("/usr/bin/timeout --kill-after", helper)
        self.assertIn("< /dev/null", helper)

        body = "\n".join(
            line for line in helper.splitlines() if not line.lstrip().startswith("#")
        )
        for command in (
            "podman",
            "flock",
            "grep",
            "sleep",
            "mktemp",
            "date",
            "timeout",
            "cat",
            "mkdir",
            "awk",
            "rm",
        ):
            self.assertIsNone(
                re.search(rf"(?<![\w./-]){command}(?=\s)", body),
                f"{command} must be called through an absolute path",
            )

    def test_nextcloud_volume_has_a_container_file_context_rule(self):
        """Host-written backups need the right SELinux label from birth.

        The disk holding nextcloud_path matches no shipped file context rule,
        so its policy default is default_t and the container is denied getattr
        on anything the host writes there after podman's :Z relabel ran.
        """
        tasks = yaml.safe_load(
            (REPO_ROOT / "roles" / "nextcloud" / "tasks" / "main.yml").read_text(
                encoding="utf-8"
            )
        )
        fcontexts = [
            task["community.general.sefcontext"]
            for task in tasks
            if "community.general.sefcontext" in task
        ]
        self.assertTrue(
            any(
                fcontext["target"] == "{{ nextcloud_path }}(/.*)?"
                and fcontext["setype"] == "container_file_t"
                for fcontext in fcontexts
            ),
            "the nextcloud role must label its volume as container content",
        )

        restores = restorecon_commands(tasks)
        self.assertTrue(restores, "the role must restore contexts on the data tree")
        for command in restores:
            self.assertIn("{{ nextcloud_path }}/data", command)
            self.assertNotRegex(
                command,
                r"-[A-Za-z]*F",
                "forcing the range would strip the MCS categories podman's :Z applied",
            )
            self.assertRegex(
                command,
                r"\|\s*wc -l",
                "restorecon -v prints a line per relabeled file, and returning the "
                "whole data tree's worth kills the Ansible worker the runner "
                "container runs inside its memory-capped container",
            )

    def test_scan_helper_confirms_the_path_reached_the_file_cache(self):
        """files:scan can exit zero without indexing the backup at all."""
        helper = NEXTCLOUD_SCAN_HELPER.read_text(encoding="utf-8")
        self.assertIn("occ info:file", helper)
        self.assertIn("path_is_indexed", helper)

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
        for role in ("vaultwarden", "playbook_runner", "music_server"):
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


class RootlessPodmanPipelineTests(unittest.TestCase):
    """The validation pipeline runs on rootless Podman and nothing else.

    Supporting a second engine meant detecting which one was in use and mapping
    uids two different ways per engine, and a wrong answer there is silent: the
    gate runs as an unowned subuid and dies on a permission error somewhere
    inside the working tree. These guards keep a Docker path from creeping
    back in and keep the uid mapping intact.
    """

    PIPELINE_SCRIPTS = (
        "scripts/toolbox.sh",
        "scripts/run-runtime-container-tests.sh",
        "scripts/test_container_security.sh",
    )

    def script(self, relative_path: str) -> str:
        return (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    def test_pipeline_scripts_invoke_no_docker_engine(self):
        # Matches the engine as a command or as a variable holding one, but not
        # the word inside a comment, an image reference, or a Dockerfile path.
        docker_engine = re.compile(
            r"(?<![\w./-])docker(?![\w./-])(?=\s+(?:run|build|info|images|inspect|rm|rmi|exec|version|--))"
            r"|\bDOCKER=|\$DOCKER\b|\bcommand -v docker\b"
        )
        for relative_path in self.PIPELINE_SCRIPTS:
            with self.subTest(script=relative_path):
                for number, line in enumerate(self.script(relative_path).splitlines(), 1):
                    if line.lstrip().startswith("#"):
                        continue
                    self.assertIsNone(
                        docker_engine.search(line),
                        f"{relative_path}:{number} reaches for Docker: {line.strip()}",
                    )

    def test_pipeline_scripts_require_a_rootless_engine(self):
        for relative_path in ("scripts/toolbox.sh", "scripts/run-runtime-container-tests.sh"):
            with self.subTest(script=relative_path):
                self.assertIn(
                    "{{.Host.Security.Rootless}}",
                    self.script(relative_path),
                    "a rootful engine has to be rejected, not mapped around",
                )

    def test_toolbox_maps_the_callers_uid_into_the_container(self):
        toolbox = self.script("scripts/toolbox.sh")
        self.assertIn("--userns=keep-id", toolbox)
        self.assertRegex(
            toolbox,
            r'--user "\$\(id -u\):\$\(id -g\)"',
            "keep-id is what makes --user name the caller rather than a subuid; "
            "both are needed for a gate's writes to stay owned by them",
        )

    def test_runtime_suite_hands_fixtures_back_through_the_user_namespace(self):
        suite = self.script("scripts/test_container_security.sh")
        self.assertIn("$PODMAN unshare chown", suite)
        self.assertNotIn(
            "$(id -u):$(id -g)",
            suite,
            "under rootless Podman the caller is 0:0 inside the namespace; "
            "naming their host uid there resolves to a subuid instead",
        )

    def test_toolbox_image_carries_a_podman_client(self):
        dockerfile = (REPO_ROOT / "tools" / "toolbox" / "Dockerfile").read_text(
            encoding="utf-8"
        )
        self.assertIn("podman-remote", dockerfile)
        self.assertNotIn("docker-cli", dockerfile)


class AnsibleRegressionTests(unittest.TestCase):

    def test_convergence_applies_the_full_os_update_set(self):
        tasks = yaml.safe_load(
            (REPO_ROOT / "roles" / "standard_update_packages" / "tasks" / "main.yml")
            .read_text(encoding="utf-8")
        )
        updates = [
            task["ansible.builtin.dnf"]
            for task in tasks
            if task.get("ansible.builtin.dnf", {}).get("name") == "*"
        ]
        self.assertTrue(updates, "no dnf task updates the installed package set")
        for update in updates:
            self.assertFalse(
                update.get("security", False),
                "the weekly patch run applies every Rocky update, not only errata",
            )
        self.assertIs(
            role_defaults("standard_update_packages")["standard_update_apply_full_updates"],
            True,
        )

    def test_weekly_patch_run_converges_vm1_then_reboots(self):
        plays = yaml.safe_load((REPO_ROOT / "vm1.yml").read_text(encoding="utf-8"))
        self.assertIn("standard_update_packages", plays[0]["roles"])
        imports = [
            play["import_playbook"]
            for play in yaml.safe_load(
                (REPO_ROOT / "update_homelab_vms.yml").read_text(encoding="utf-8")
            )
        ]
        self.assertEqual(
            imports,
            ["homelab_vms.yml", "reboot_vms.yml"],
            "kernel and library updates only take effect after the reboot",
        )

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
        command = matching[0]["ansible.builtin.shell"]["cmd"]
        self.assertEqual(command.count("find"), 1)
        self.assertRegex(
            command,
            r"\|\s*wc -l",
            "-print emits a line per fixed file, and returning a populated tree's "
            "worth kills the Ansible worker the runner container runs "
            "inside its memory-capped container",
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child_directory = root / "directory"
            child_file = child_directory / "file"
            child_directory.mkdir(mode=0o700)
            child_file.write_text("content", encoding="utf-8")
            child_file.chmod(0o600)
            rendered = (
                command.replace("{{ item | quote }}", shlex.quote(str(root)))
                .replace("{{ nextcloud_user_files_directory_mode }}", "0770")
                .replace("{{ nextcloud_user_files_file_mode }}", "0660")
            )
            self.assertNotIn("{{", rendered)
            runs = [
                subprocess.run(
                    rendered,
                    shell=True,
                    executable="/bin/bash",
                    check=True,
                    capture_output=True,
                    text=True,
                )
                for _ in range(2)
            ]
            directory_mode = child_directory.stat().st_mode & 0o777
            file_mode = child_file.stat().st_mode & 0o777

        self.assertGreater(int(runs[0].stdout.strip()), 0)
        self.assertEqual(runs[1].stdout.strip(), "0")
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
        "paperless_ngx": {"paperless_proxy_net": True},
        "vaultwarden": {"vaultwarden_container_net": True},
        "playbook_runner": {
            "playbook_runner_container_net": True,
            "{{ playbook_runner_egress_network }}": False,
        },
        "music_server": {"music_server_container_net": True},
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
        """Only the deliberate egress networks may reach the host network."""
        external = {
            (role, name)
            for role, networks in self.EXPECTED_NETWORKS.items()
            for name, internal in networks.items()
            if not internal
        }
        self.assertEqual(
            external,
            {
                ("playbook_runner", "{{ playbook_runner_egress_network }}"),
                ("reverse_proxy", "{{ traefik_egress_network }}"),
            },
        )

    def test_control_plane_networks_are_created_but_not_replaced_by_the_proxy(self):
        """Replacing playbook_runner_container_net from reverse_proxy would cut the
        playbook-runner container running the playbook, so only the
        playbook_runner role may repair drift on it."""
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
            "playbook_runner_container_net",
            defaults["reverse_proxy_deferred_route_networks"],
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

    def test_deferred_replacement_preserves_declared_network_mode(self):
        queue = next(
            task
            for task in role_tasks("container_network")
            if task["name"].startswith("Queue container network")
        )
        request = queue["vars"]["container_network_migration_request"]
        self.assertEqual(request["internal"], "{{ container_network_internal }}")


class PlaybookRunnerTests(unittest.TestCase):
    """Guards for the first-party Ansible web UI and scheduler.

    The runner holds every automation secret, so its container is the most
    sensitive one on VM1: the master key arrives only as a Podman secret,
    the scratch space that holds decrypted inventories is a noexec tmpfs, and
    memory is capped without swap so secrets are never paged to disk.
    """

    def setUp(self):
        self.tasks = role_tasks("playbook_runner")
        self.script = (
            REPO_ROOT / "roles" / "playbook_runner" / "templates" / "playbook_runner.sh.j2"
        ).read_text(encoding="utf-8")

    def test_role_is_off_unless_enabled(self):
        self.assertIs(role_defaults("playbook_runner")["playbook_runner_enabled"], False)
        first = self.tasks[0]
        self.assertEqual(first.get("ansible.builtin.meta"), "end_role")
        self.assertIn("playbook_runner_enabled", first["when"])

    def test_runner_image_is_approved_only_when_enabled(self):
        play = yaml.safe_load((REPO_ROOT / "vm1.yml").read_text(encoding="utf-8"))[0]
        approved = play["vars"]["approved_container_images"]
        self.assertIn("[playbook_runner_image] if playbook_runner_enabled", approved)
        self.assertIs(play["vars"]["playbook_runner_enabled"], True, "VM1 runs playbook-runner")
        self.assertIn("if 'playbook_runner' in artifact_locked_images", play["vars"]["playbook_runner_image"])
        roles = play["roles"]
        self.assertLess(roles.index("nextcloud"), roles.index("playbook_runner"))
        self.assertLess(roles.index("playbook_runner"), roles.index("standard_cleanup"))

    def test_secret_tasks_hide_their_values(self):
        for task in self.tasks:
            text = yaml.safe_dump(task)
            if "playbook_runner_master_key" in text and (
                "content" in text or "assert" in text
            ):
                with self.subTest(task=task["name"]):
                    self.assertIs(task.get("no_log"), True)
            if "playbook_runner_admin_password" in text and "content" in text:
                with self.subTest(task=task["name"]):
                    self.assertIs(task.get("no_log"), True)

    def test_master_key_is_a_podman_secret_never_an_env_var(self):
        self.assertIn("--secret playbook_runner_master_key,target=/run/secrets/", self.script)
        self.assertIn("mode=0400", self.script)
        self.assertNotIn("PR_MASTER_KEY", self.script)
        self.assertNotIn("--env-file", self.script)

    def test_container_is_hardened(self):
        for flag in (
            "--pull=never",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--memory=512m",
            "--memory-swap=512m",
            "destination=/run/playbook-runner,tmpfs-size=256M,tmpfs-mode=0700,U=true,noexec",
        ):
            with self.subTest(flag=flag):
                self.assertIn(flag, self.script)
        self.assertNotIn("--cap-add", self.script)
        self.assertNotRegex(self.script, r"(^|\s)-p ")

    def test_runner_never_joins_the_backend_network(self):
        self.assertNotIn("nextcloud_container_net", self.script)


class NetworkPlanTests(unittest.TestCase):
    """Guards for network/vm1.yml, the one VM1 container address plan.

    It replaced the route dictionaries every inventory had to repeat in full
    (inventory values replace role defaults rather than merging with them).
    """

    def setUp(self):
        self.plan = yaml.safe_load((REPO_ROOT / "network" / "vm1.yml").read_text(encoding="utf-8"))

    def test_vm1_loads_the_plan(self):
        play = yaml.safe_load((REPO_ROOT / "vm1.yml").read_text(encoding="utf-8"))[0]
        self.assertIn("network/vm1.yml", play["vars_files"])

    def test_every_route_network_has_both_addresses_inside_its_subnet(self):
        subnets = self.plan["route_proxy_network_subnets"]
        services = self.plan["route_proxy_container_ips"]
        traefik = self.plan["route_proxy_traefik_ips"]
        self.assertEqual(set(subnets), set(services))
        self.assertEqual(set(subnets), set(traefik))
        for net, cidr in subnets.items():
            network = ipaddress.ip_network(cidr)
            with self.subTest(network=net):
                self.assertIn(ipaddress.ip_address(services[net]), network)
                self.assertIn(ipaddress.ip_address(traefik[net]), network)
                self.assertNotEqual(services[net], traefik[net])

    def test_subnets_do_not_overlap_each_other_or_the_backend(self):
        networks = [ipaddress.ip_network(c) for c in self.plan["route_proxy_network_subnets"].values()]
        networks.append(ipaddress.ip_network("172.16.1.0/28"))
        for i, a in enumerate(networks):
            for b in networks[i + 1 :]:
                with self.subTest(a=str(a), b=str(b)):
                    self.assertFalse(a.overlaps(b))

    def test_no_address_is_assigned_twice(self):
        static = self.plan["container_static_ips"]
        traefik = list(self.plan["route_proxy_traefik_ips"].values())
        self.assertEqual(len(set(static.values())), len(static))
        self.assertFalse(set(static.values()) & set(traefik))
        self.assertTrue(set(self.plan["route_proxy_container_ips"].values()) <= set(static.values()))

    def test_routes_cover_every_route_network(self):
        routes = self.plan["proxy_config"]
        names = [r["name"] for r in routes]
        self.assertEqual(len(set(names)), len(names))
        self.assertEqual(
            {r["proxy_network"] for r in routes}, set(self.plan["route_proxy_network_subnets"])
        )
        for route in routes:
            with self.subTest(route=route["name"]):
                self.assertTrue(route["proxy_fqdn"].endswith(".{{ homelab_internal_domain }}"))
                self.assertIn("container_dns.aliases.", route["container_destination"])

    def test_every_route_is_management_only(self):
        """VM1 serves only the user LAN and the VPN (management_network)."""
        for route in self.plan["proxy_config"]:
            with self.subTest(route=route["name"]):
                self.assertIs(route.get("proxy_management_only"), True)

    def test_music_route_is_unlogged(self):
        route = next(r for r in self.plan["proxy_config"] if r["name"] == "music_server_proxy")
        self.assertIs(route["proxy_access_log"], False)

    def test_role_defaults_agree_with_the_plan(self):
        keys = (
            "route_proxy_network_subnets",
            "route_proxy_container_ips",
            "route_proxy_traefik_ips",
            "container_static_ips",
        )
        for role_dir in sorted((REPO_ROOT / "roles").iterdir()):
            defaults_file = role_dir / "defaults" / "main.yml"
            if not defaults_file.exists():
                continue
            defaults = yaml.safe_load(defaults_file.read_text(encoding="utf-8")) or {}
            for key in keys:
                for name, value in (defaults.get(key) or {}).items():
                    with self.subTest(role=role_dir.name, key=key, name=name):
                        self.assertEqual(self.plan[key].get(name), value)
            for alias, value in ((defaults.get("container_dns") or {}).get("aliases") or {}).items():
                with self.subTest(role=role_dir.name, alias=alias):
                    self.assertEqual(self.plan["container_dns"]["aliases"].get(alias), value)


class MusicServerTests(unittest.TestCase):
    """Guards for the first-party Subsonic music server.

    Its users file carries every account's password, so it arrives only as a
    Podman secret; the music is mounted read-only; and the container has no
    network but the internal one Traefik reaches it on.
    """

    def setUp(self):
        self.tasks = role_tasks("music_server")
        self.script = (
            REPO_ROOT / "roles" / "music_server" / "templates" / "music_server.sh.j2"
        ).read_text(encoding="utf-8")

    def test_role_is_off_unless_enabled(self):
        self.assertIs(role_defaults("music_server")["music_server_enabled"], False)
        first = self.tasks[0]
        self.assertEqual(first.get("ansible.builtin.meta"), "end_role")
        self.assertIn("music_server_enabled", first["when"])

    def test_vm1_enables_it_only_with_a_locked_image(self):
        play = yaml.safe_load((REPO_ROOT / "vm1.yml").read_text(encoding="utf-8"))[0]
        locked = "'approved_digest' in artifact_locked_images.music_server | default({})"
        self.assertIn(locked, play["vars"]["music_server_enabled"])
        self.assertIn(f"if {locked}", play["vars"]["music_server_image"])
        self.assertIn("[music_server_image] if music_server_enabled", play["vars"]["approved_container_images"])
        roles = play["roles"]
        self.assertLess(roles.index("reverse_proxy"), roles.index("music_server"))
        self.assertLess(roles.index("nextcloud"), roles.index("music_server"))
        self.assertLess(roles.index("music_server"), roles.index("standard_cleanup"))

    def test_vm1_orders_its_unit_only_when_enabled(self):
        play = yaml.safe_load((REPO_ROOT / "vm1.yml").read_text(encoding="utf-8"))[0]
        names = play["vars"]["container_service_names"]
        self.assertIn("['music_server'] if music_server_enabled", names)
        self.assertIn("['playbook_runner'] if playbook_runner_enabled", names)
        for unit in ("postgres_container", "redis_container", "nextcloud_container", "paperless_ngx", "vaultwarden"):
            with self.subTest(unit=unit):
                self.assertIn(f"'{unit}'", names)

    def test_secret_tasks_hide_their_values(self):
        for task in self.tasks:
            text = yaml.safe_dump(task)
            if ("music_server_master_key" in text or "music_server_users" in text) and (
                "content" in text or "assert" in text
            ):
                with self.subTest(task=task["name"]):
                    self.assertIs(task.get("no_log"), True)

    def test_secrets_are_podman_secrets_never_env_vars(self):
        self.assertIn("--secret music_server_master_key,target=/run/secrets/", self.script)
        self.assertIn("--secret music_server_users,target=/run/secrets/", self.script)
        self.assertNotIn("MS_MASTER_KEY", self.script)
        self.assertNotIn("--env-file", self.script)

    def test_container_is_hardened(self):
        for flag in (
            "--pull=never",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--memory={{ music_server_memory }}",
            "--memory-swap={{ music_server_memory }}",
            "--tmpfs /tmp:rw,noexec,nosuid,nodev",
            ":/music:ro,z",
        ):
            with self.subTest(flag=flag):
                self.assertIn(flag, self.script)
        self.assertNotIn("--cap-add", self.script)
        self.assertNotRegex(self.script, r"(^|\s)-p ")
        self.assertEqual(role_defaults("music_server")["music_server_memory"], "512m")

    def test_only_the_internal_route_network(self):
        self.assertEqual(self.script.count("--network="), 1)
        self.assertIn("--network=music_server_container_net:", self.script)

    def test_routes_can_leave_the_access_log(self):
        """Subsonic credentials travel in the query string, which Traefik's
        access log records unless the route opts out."""
        template = (
            REPO_ROOT / "roles" / "reverse_proxy" / "templates" / "service_proxy.yml.j2"
        ).read_text(encoding="utf-8")
        self.assertIn("proxy_access_log", template)
        self.assertIn("accessLogs: false", template)


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
            roles.index("container_network_migration"), roles.index("playbook_runner")
        )
        self.assertGreater(
            roles.index("container_network_migration"), roles.index("standard_cleanup")
        )

        runner_tasks = (
            REPO_ROOT / "roles" / "playbook_runner" / "tasks" / "main.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Schedule deferred container network migration", runner_tasks)

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

    def test_migration_recreates_the_declared_internal_mode(self):
        create_line = next(
            line
            for line in self.script.splitlines()
            if line.strip().startswith("/usr/bin/podman network create")
        )
        self.assertIn("network.internal | default(true) | bool", create_line)
        self.assertNotIn("network create --internal --subnet", create_line)


if __name__ == "__main__":
    unittest.main()


class CheckModeTests(unittest.TestCase):
    """Check mode skips command, shell, and tempfile tasks, leaving a
    registered result with no rc, stdout, or path. Tasks whose result feeds
    later tasks must therefore opt in to running."""

    PROBE_MODULES = {
        "ansible.builtin.command",
        "ansible.builtin.shell",
        "ansible.builtin.tempfile",
    }

    def iter_tasks(self, tasks):
        for task in tasks or []:
            yield task
            for key in ("block", "rescue", "always"):
                yield from self.iter_tasks(task.get(key))

    def test_registered_probes_run_in_check_mode(self):
        offenders = []
        for path in sorted((REPO_ROOT / "roles").glob("*/tasks/*.yml")):
            tasks = yaml.safe_load(path.read_text(encoding="utf-8")) or []
            for task in self.iter_tasks(tasks):
                module = next((m for m in self.PROBE_MODULES if m in task), None)
                if module is None or "register" not in task:
                    continue
                read_only = (
                    module == "ansible.builtin.tempfile"
                    or task.get("changed_when") is False
                )
                if read_only and task.get("check_mode") is not False:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {task.get('name')}")
        self.assertEqual(
            offenders,
            [],
            "Read-only registered tasks need check_mode: false so --check "
            "does not leave their results empty",
        )


class RetireSemaphoreTests(unittest.TestCase):
    """The one-shot cleanup for the retired Semaphore install."""

    def setUp(self):
        self.play = yaml.safe_load(
            (REPO_ROOT / "retire_semaphore.yml").read_text(encoding="utf-8")
        )[0]
        self.tasks = {task["name"]: task for task in self.play["tasks"]}

    def test_it_is_never_part_of_the_weekly_chain(self):
        """It deletes a database, so it must be run on purpose."""
        for playbook in ("vm1.yml", "homelab_vms.yml", "update_homelab_vms.yml"):
            with self.subTest(playbook=playbook):
                self.assertNotIn(
                    "retire_semaphore",
                    (REPO_ROOT / playbook).read_text(encoding="utf-8"),
                )

    def test_read_only_probes_run_in_check_mode(self):
        for name in ("List Semaphore images", "Check for Semaphore networks"):
            with self.subTest(task=name):
                self.assertIs(self.tasks[name]["check_mode"], False)

    def test_database_is_dropped_only_when_it_is_named(self):
        conditions = self.tasks["Drop the Semaphore database and role"]["when"]
        self.assertIn("retire_semaphore_database | length > 0", conditions)
        self.assertIn("retire_semaphore_db_user | length > 0", conditions)

    def test_names_are_validated_before_anything_is_removed(self):
        self.assertEqual(
            next(iter(self.tasks)), "Validate cleanup inputs"
        )

    def test_it_removes_every_artifact_the_role_created(self):
        paths = "\n".join(self.play["vars"]["retire_semaphore_paths"])
        for artifact in (
            "semaphore.service",
            "semaphore.sh",
            "backup_semaphore.sh",
            "/etc/semaphore",
            "/var/lib/semaphore",
            "semaphore.env",
            "semaphore_backup.log",
        ):
            with self.subTest(artifact=artifact):
                self.assertIn(artifact, paths)
        self.assertEqual(
            self.tasks["Remove the Semaphore backup cron entry"]["ansible.builtin.cron"],
            {"name": "Backup Semaphore", "state": "absent"},
        )
