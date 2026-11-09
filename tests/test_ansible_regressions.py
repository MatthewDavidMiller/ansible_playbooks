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


class DataDiskTests(unittest.TestCase):
    """The data disk is mounted by a role of its own."""

    def test_the_data_disk_is_mounted_by_its_own_role_before_any_role_uses_it(self):
        """A directory made before the mount lands on the OS disk under it, and
        a mount owned by a service role would go when that service is removed."""
        tasks = role_tasks("data_disk")
        mounts = [t for t in tasks if "ansible.posix.mount" in t]
        self.assertEqual(len(mounts), 1)
        self.assertEqual(mounts[0]["ansible.posix.mount"]["path"], "{{ data_disk_mount_path }}")
        self.assertEqual(mounts[0]["ansible.posix.mount"]["opts"], "rw,auto", "opts that differ remount the disk")
        self.assertFalse(
            [t for t in role_tasks("music_server") if "ansible.posix.mount" in t],
            "the data disk is mounted only by the data_disk role",
        )
        # homedrive mounts only a disk of its own (homedrive_disk), never the shared one.
        own = [t for t in role_tasks("homedrive") if "ansible.posix.mount" in t]
        self.assertEqual([t["when"] for t in own], ["homedrive_disk | length > 0"])
        play = yaml.safe_load((REPO_ROOT / "vm1.yml").read_text(encoding="utf-8"))[0]
        roles = play["roles"]
        for user in ("music_server", "homedrive"):
            with self.subTest(user=user):
                self.assertLess(roles.index("data_disk"), roles.index(user))
        self.assertEqual(mounts[0]["ansible.posix.mount"]["state"], "mounted")

    def test_the_data_disk_is_set_by_its_own_variables(self):
        defaults = yaml.safe_load(
            (REPO_ROOT / "roles" / "data_disk" / "defaults" / "main.yml").read_text(encoding="utf-8")
        )
        self.assertEqual(defaults["data_disk"], "")
        self.assertEqual(defaults["data_disk_mount_path"], "/data_drive")

    def test_the_data_disk_role_refuses_a_missing_disk_and_checks_the_mount(self):
        tasks = role_tasks("data_disk")
        conditions = "\n".join(tasks[0]["ansible.builtin.assert"]["that"])
        self.assertIn("data_disk | length > 0", conditions)
        self.assertIn("not in ['/'", conditions)
        check = next(t for t in tasks if t["name"] == "Check the data disk is mounted")
        self.assertEqual(check["ansible.builtin.command"]["argv"][:2], ["mountpoint", "-q"])

    def test_homedrive_keeps_its_data_inside_the_data_disk(self):
        conditions = "\n".join(_first_assert("homedrive"))
        self.assertIn("homedrive_path.startswith((data_disk_mount_path", conditions)
        self.assertIn("homedrive_export_path.startswith((data_disk_mount_path", conditions)


class RetiredNextcloudStackTests(unittest.TestCase):
    """Nothing of the Nextcloud stack is deployed any more."""

    RETIRED = (
        "nextcloud",
        "paperless",
        "postgres",
        "redis",
    )

    def test_its_roles_and_images_are_gone(self):
        for role in ("nextcloud", "paperless_ngx"):
            self.assertFalse((REPO_ROOT / "roles" / role).exists(), role)
        play = yaml.safe_load((REPO_ROOT / "vm1.yml").read_text(encoding="utf-8"))[0]
        self.assertNotIn("nextcloud", play["roles"])
        self.assertNotIn("paperless_ngx", play["roles"])
        lock = yaml.safe_load((REPO_ROOT / "artifacts" / "containers.lock.yml").read_text(encoding="utf-8"))
        for image in self.RETIRED:
            self.assertNotIn(image, lock["artifact_locked_images"])
        text = "\n".join(
            str(play["vars"].get(k, "")) for k in ("container_service_names", "approved_container_images")
        )
        for unit in ("postgres", "redis", "nextcloud", "paperless"):
            self.assertNotIn(unit, text)

    def test_its_networks_routes_and_addresses_are_gone(self):
        plan = yaml.safe_load((REPO_ROOT / "network" / "vm1.yml").read_text(encoding="utf-8"))
        for section in (
            "route_proxy_network_subnets",
            "route_proxy_container_ips",
            "route_proxy_traefik_ips",
            "container_static_ips",
        ):
            for name in plan[section]:
                self.assertFalse(any(word in name for word in self.RETIRED), (section, name))
        self.assertFalse(
            any(any(word in name for word in self.RETIRED) for name in plan["container_dns"]["aliases"])
        )
        self.assertFalse(
            [r["name"] for r in plan["proxy_routes"] if any(word in r["name"] for word in self.RETIRED)]
        )

    def test_no_remaining_role_installs_into_nextcloud_or_depends_on_it(self):
        for path in sorted((REPO_ROOT / "roles").glob("*/tasks/*.yml")) + sorted(
            (REPO_ROOT / "roles").glob("*/templates/*")
        ):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                for needle in (
                    "nextcloud_scan_path",
                    "nextcloud_path",
                    "nextcloud_uid",
                    "nextcloud_container",
                    "backup_local",
                    "backup_destination",
                ):
                    self.assertNotIn(needle, text)

    def test_the_service_backups_go_only_to_homedrive(self):
        for role, script in (
            ("vaultwarden", "backup_db.j2"),
            ("playbook_runner", "backup_playbook_runner.sh.j2"),
            ("music_server", "backup_music_server.sh.j2"),
        ):
            with self.subTest(role=role):
                text = (REPO_ROOT / "roles" / role / "templates" / script).read_text(encoding="utf-8")
                self.assertIn("/usr/local/bin/homedrive_import_path.sh", text)
                self.assertNotIn("rclone", text)
                self.assertNotIn("{% if", text)
                conditions = "\n".join(_first_assert(role))
                self.assertIn("homedrive_enabled | default(false) | bool", conditions)
                self.assertIn("homedrive_backup_user in", conditions)

    def test_the_backup_role_only_prepares_the_repository(self):
        names = [t["name"] for t in role_tasks("backup")]
        self.assertEqual(
            names,
            [
                "Validate backup inputs before changing the host",
                "Install backup packages",
                "Create Borg Backup directory",
                "Mount Disk for backups",
                "Init backup repo Script",
            ],
        )
        self.assertFalse((REPO_ROOT / "roles" / "backup" / "templates" / "backup_files.sh.j2").exists())

    def test_the_rclone_config_has_only_the_homedrive_remote(self):
        text = (REPO_ROOT / "roles" / "standard_rclone" / "templates" / "rclone_config.j2").read_text(encoding="utf-8")
        self.assertNotIn("[Nextcloud]", text)
        self.assertIn("[Homedrive]", text)

    def test_homedrive_names_the_account_the_services_use(self):
        defaults = role_defaults("homedrive")
        self.assertEqual(defaults["homedrive_main_user"], "")
        self.assertEqual(defaults["homedrive_music_user"], "{{ homedrive_main_user }}")
        for role in ("vaultwarden", "playbook_runner", "music_server"):
            self.assertEqual(
                role_defaults(role)["homedrive_backup_user"], "{{ homedrive_main_user | default('') }}"
            )


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

    def test_traefik_uses_only_the_dns_server_it_can_reach(self):
        script = (
            REPO_ROOT / "roles/reverse_proxy/templates/traefik_container.sh.j2"
        ).read_text(encoding="utf-8")
        self.assertIn("(index .Subnets 0).Gateway", script, "the gateway is read at each start")
        self.assertIn("{{ traefik_egress_network }}", script)
        self.assertIn("/etc/resolv.conf:Z,ro", script)
        self.assertIn(
            '"${resolv_mount[@]}"',
            script.split("exec /usr/bin/podman run")[1],
            "an unreadable gateway must not stop Traefik",
        )

    def test_reboot_is_delayed_and_its_failure_fails_the_run(self):
        plays = yaml.safe_load((REPO_ROOT / "reboot_vms.yml").read_text(encoding="utf-8"))
        task = plays[0]["tasks"][0]
        self.assertIn("+1", task["ansible.builtin.command"], "the runner lives on VM1")
        self.assertNotIn("poll", task, "with poll: 0 a failed shutdown reports success")
        self.assertNotIn("async", task)

    def test_show_logs_covers_every_container_and_changes_nothing(self):
        play = yaml.safe_load((REPO_ROOT / "show_logs.yml").read_text(encoding="utf-8"))[0]
        shown = {
            task["vars"]["show_logs_container"]: task
            for task in play["tasks"]
            if "ansible.builtin.import_tasks" in task
        }
        started = set()
        for template in (REPO_ROOT / "roles").glob("*/templates/*.j2"):
            started.update(
                re.findall(r"--name[= ]([a-z_]+) ", template.read_text(encoding="utf-8"))
            )
        self.assertEqual(set(shown), started, "a new container needs a section here")
        for name, task in shown.items():
            self.assertEqual(task["tags"], [name], "the tag is how a template picks it")
            unit = task["vars"]["show_logs_unit"] + ".service.j2"
            self.assertTrue(list((REPO_ROOT / "roles").glob(f"*/templates/{unit}")), unit)
        reads = [t for t in play["tasks"] if "ansible.builtin.shell" in t]
        reads += yaml.safe_load(
            (REPO_ROOT / "standalone_tasks/show_service_logs.yml").read_text(encoding="utf-8")
        )[:1]
        for task in reads:
            self.assertIs(task["changed_when"], False)
            self.assertIs(task["failed_when"], False, "a stopped service is what it reports")
            self.assertIs(task["check_mode"], False, "or check mode shows nothing")


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
        "vaultwarden": {"vaultwarden_container_net": True},
        "playbook_runner": {
            "playbook_runner_container_net": True,
            "{{ playbook_runner_egress_network }}": False,
        },
        "music_server": {"music_server_container_net": True},
        "homedrive": {"homedrive_container_net": True},
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

    def all_routes(self):
        return self.plan["proxy_routes"] + self.plan["homedrive_routes"]

    def test_homedrive_route_exists_only_when_enabled(self):
        """Without homedrive_deploy, Traefik must get no route, network, or
        certificate for homedrive."""
        self.assertEqual(
            self.plan["proxy_config"],
            "{{ proxy_routes + (homedrive_routes if homedrive_enabled | bool else []) }}",
        )
        self.assertNotIn("homedrive_proxy", [r["name"] for r in self.plan["proxy_routes"]])

    def test_routes_cover_every_route_network(self):
        routes = self.all_routes()
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
        for route in self.all_routes():
            with self.subTest(route=route["name"]):
                self.assertIs(route.get("proxy_management_only"), True)

    def test_music_route_is_unlogged(self):
        route = next(r for r in self.all_routes() if r["name"] == "music_server_proxy")
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
        self.assertLess(roles.index("music_server"), roles.index("standard_cleanup"))

    def test_vm1_orders_its_unit_only_when_enabled(self):
        play = yaml.safe_load((REPO_ROOT / "vm1.yml").read_text(encoding="utf-8"))[0]
        names = play["vars"]["container_service_names"]
        self.assertIn("['music_server'] if music_server_enabled", names)
        self.assertIn("['playbook_runner'] if playbook_runner_enabled", names)
        for unit in ("vaultwarden",):
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


class HomedriveTests(unittest.TestCase):
    """Guards for the first-party file sync server.

    Its store must never be created by accident: an unmounted disk looks
    like an empty directory, so creating the store is an explicit, one-run
    flag, and the role refuses a store path without a store.id otherwise.
    """

    def setUp(self):
        self.tasks = role_tasks("homedrive")
        self.script = (
            REPO_ROOT / "roles" / "homedrive" / "templates" / "homedrive.sh.j2"
        ).read_text(encoding="utf-8")
        self.play = yaml.safe_load((REPO_ROOT / "vm1.yml").read_text(encoding="utf-8"))[0]

    def test_paths_the_drill_deletes_cannot_overlap_kept_data(self):
        """The drill empties its scratch space; the role refuses a scratch,
        store, backup or export path inside another."""
        assert_task = role_tasks("homedrive")[1]["ansible.builtin.assert"]
        joined = "\n".join(assert_task["that"])
        self.assertIn(
            "[homedrive_path, homedrive_borg_repo, homedrive_drill_path, homedrive_export_path] | homelab_paths_disjoint",
            joined,
        )
        self.assertIn("homedrive_trash_days | int >= 7", joined)
        self.assertIn("homedrive_keep_all_days | int >= 7", joined)

    def test_role_is_off_unless_enabled(self):
        self.assertIs(role_defaults("homedrive")["homedrive_enabled"], False)
        first = self.tasks[0]
        self.assertEqual(first.get("ansible.builtin.meta"), "end_role")
        self.assertIn("homedrive_enabled", first["when"])

    def test_backup_reads_metadata_first_and_leaves_out_the_history(self):
        """A journal copied after the objects can name objects the copy
        lacks; a restored store that kept its history.id would let sync
        clients trust a history the restore went back on."""
        backup = (
            REPO_ROOT / "roles" / "homedrive" / "templates" / "backup_homedrive.sh.j2"
        ).read_text(encoding="utf-8")
        self.assertIn('PATHS=("$STORE/meta")', backup)
        self.assertIn('[ "$entry" != "$STORE/meta" ]', backup)
        self.assertIn('"${PATHS[@]}"', backup)
        self.assertIn('--exclude "$STORE/history.id"', backup)
        checkpoint = backup.index("hd-server checkpoint")
        self.assertLess(checkpoint, backup.index("borg create"))

    def test_repair_helper_is_installed_root_only(self):
        task = next(t for t in self.tasks if t.get("name") == "Homedrive repair helper for disk damage")
        template = task["ansible.builtin.template"]
        self.assertEqual(template["dest"], "/usr/local/bin/homedrive_repair.sh")
        self.assertEqual((template["owner"], template["mode"]), ("root", "0700"))

    def test_vm1_needs_both_the_inventory_flag_and_a_locked_image(self):
        enabled = self.play["vars"]["homedrive_enabled"]
        self.assertIn("homedrive_deploy | default(false) | bool", enabled)
        self.assertIn("'approved_digest' in artifact_locked_images.homedrive | default({})", enabled)
        self.assertIn("[homedrive_image] if homedrive_enabled", self.play["vars"]["approved_container_images"])
        self.assertIn("['homedrive'] if homedrive_enabled", self.play["vars"]["container_service_names"])
        roles = self.play["roles"]
        self.assertLess(roles.index("reverse_proxy"), roles.index("homedrive"))
        self.assertLess(roles.index("homedrive"), roles.index("standard_cleanup"))

    def test_the_store_is_created_only_on_request(self):
        self.assertIs(role_defaults("homedrive")["homedrive_init_store"], False)
        init = next(t for t in self.tasks if "Create the homedrive store (first" in t["name"])
        self.assertIn("homedrive_init_store | bool", init["when"])
        self.assertIn("not homedrive_store_id.stat.exists", init["when"])
        refuse = next(t for t in self.tasks if t["name"] == "Refuse a store path that is not a store")
        self.assertIn(
            "homedrive_store_id.stat.exists or homedrive_init_store | bool",
            refuse["ansible.builtin.assert"]["that"],
        )
        create = next(t for t in self.tasks if t["name"] == "Create the homedrive store directory")
        self.assertNotIn("recurse", create["ansible.builtin.file"])

    def test_users_file_carries_quotas_and_validates_them(self):
        render = next(t for t in self.tasks if t["name"] == "Homedrive users file source")
        self.assertIn("'quota_gb'", render["ansible.builtin.copy"]["content"])
        validate = next(t for t in self.tasks if t["name"].startswith("Validate homedrive inputs"))
        checks = "\n".join(validate["ansible.builtin.assert"]["that"])
        self.assertIn("rejectattr('quota_gb', 'defined')", checks, "every account needs a quota")

    def test_backup_passphrase_is_root_only_and_hidden(self):
        task = next(t for t in self.tasks if t["name"] == "Homedrive backup passphrase")
        self.assertIs(task.get("no_log"), True)
        self.assertEqual(task["ansible.builtin.copy"]["mode"], "0600")
        self.assertEqual(role_defaults("homedrive")["homedrive_borg_passphrase"], "", "unencrypted unless asked")

    def test_secret_tasks_hide_their_values(self):
        for task in self.tasks:
            text = yaml.safe_dump(task)
            if "homedrive_users" in text and ("content" in text or "assert" in text):
                with self.subTest(task=task["name"]):
                    self.assertIs(task.get("no_log"), True)

    def test_container_is_hardened_and_internal(self):
        for flag in (
            "--pull=never",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--memory={{ homedrive_memory }}",
            "--memory-swap={{ homedrive_memory }}",
            "--tmpfs /tmp:rw,noexec,nosuid,nodev",
            "--secret homedrive_users,target=/run/secrets/",
        ):
            with self.subTest(flag=flag):
                self.assertIn(flag, self.script)
        self.assertNotIn("--cap-add", self.script)
        self.assertNotRegex(self.script, r"(^|\s)-p ")
        self.assertEqual(self.script.count("--network="), 1)
        self.assertIn("--network=homedrive_container_net:", self.script)

    def test_images_pull_anonymously(self):
        """Every approved image, homedrive's included, is public: VM1 holds
        no registry credentials."""
        tasks = role_tasks("standard_podman")
        pull = next(t for t in tasks if t["name"] == "Pull approved images into the local podman store")
        self.assertEqual(pull["ansible.builtin.command"]["argv"], ["podman", "pull", "{{ item.item }}"])
        self.assertNotIn("container_registry_credentials", role_defaults("standard_podman") or {})
        for task in tasks:
            self.assertNotIn("registry-auth", str(task))


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


class RetiredNavidromeTests(unittest.TestCase):
    """Navidrome is gone from the maintained tree."""

    def test_navidrome_is_gone_from_the_maintained_tree(self):
        """Only the history documents and the network plan may name it."""
        allowed = {
            "docs/guides/music-server-migration.md",
            "docs/architecture-decisions.md",
            "docs/archive.md",
            "docs/index.md",
            "network/vm1.yml",
            "tests/test_ansible_regressions.py",
        }
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout.split()
        for name in tracked:
            path = REPO_ROOT / name
            if name in allowed or not path.is_file() or path.suffix not in {".yml", ".yaml", ".j2", ".sh", ".py", ".md", ".cfg"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            with self.subTest(path=name):
                self.assertFalse("navidrome" in text, f"{name} still mentions Navidrome")


class HomedriveImportTests(unittest.TestCase):
    """The one-shot bulk load of the previous file service into homedrive."""

    def setUp(self):
        self.play = yaml.safe_load(
            (REPO_ROOT / "homedrive_import.yml").read_text(encoding="utf-8")
        )[0]
        self.tasks = {task["name"]: task for task in self.play["tasks"]}
        self.names = list(self.tasks)
        self.facts = self.tasks["Set the one-off container command"]["ansible.builtin.set_fact"]

    def test_it_is_never_part_of_the_weekly_chain(self):
        for playbook in ("vm1.yml", "homelab_vms.yml", "update_homelab_vms.yml"):
            with self.subTest(playbook=playbook):
                self.assertNotIn(
                    "homedrive_import",
                    (REPO_ROOT / playbook).read_text(encoding="utf-8"),
                )

    def test_inputs_are_validated_first(self):
        self.assertEqual(self.names[1], "Validate import inputs")

    def test_nothing_is_written_before_the_missing_count_is_checked(self):
        """A wrong user or source would load a whole second copy."""
        self.assertLess(
            self.names.index("Find what the drive lacks (read-only, by size)"),
            self.names.index("Stop if far more is missing than expected"),
        )
        self.assertLess(
            self.names.index("Stop if far more is missing than expected"),
            self.names.index("Import the missing files"),
        )

    def test_a_run_without_tags_reads_only_what_is_missing(self):
        """Reading the whole tree took hours for six missing files."""
        for name in (
            "Find what the drive lacks (read-only, by size)",
            "Check nothing is missing now (by size)",
        ):
            with self.subTest(task=name):
                self.assertIn("verify-tree --quick", self.tasks[name]["ansible.builtin.shell"]["cmd"])
        self.assertIn(
            "import-tree --only-missing",
            self.tasks["Import the missing files"]["ansible.builtin.shell"]["cmd"],
        )
        for task in self.play["tasks"]:
            command = str(task.get("ansible.builtin.shell", {}).get("cmd", ""))
            reads_everything = "hd-server fsck" in command or (
                "verify-tree " in command and "--quick" not in command
            )
            if reads_everything:
                with self.subTest(task=task["name"]):
                    self.assertIn("never", task["tags"])
                    self.assertIn("full", task["tags"])

    def test_the_source_folder_follows_the_users_new_variable_name(self):
        """Inventory moved off nextcloud_homelab_user keeps the source path."""
        facts = self.tasks["Apply the defaults for what the inventory leaves unset"][
            "ansible.builtin.set_fact"
        ]
        self.assertIn("homedrive_main_user", facts["homedrive_import_src"])
        self.assertIn("homedrive_main_user", facts["homedrive_import_user"])

    def test_setup_runs_whatever_the_tags(self):
        for name in self.names[: self.names.index("Set the one-off container command") + 1]:
            with self.subTest(task=name):
                self.assertIn("always", self.tasks[name]["tags"])

    def test_the_one_off_container_relabels_nothing_and_writes_only_its_cache(self):
        """A :Z on the store would take it away from the running server."""
        run = self.facts["homedrive_import_run"]
        self.assertIn("/var/lib/homedrive:ro", run)
        self.assertIn("/mnt/src:ro", run)
        self.assertIn(":/mnt/cache", run)
        self.assertIn("--network=none", run)
        self.assertIn("--read-only", run)
        self.assertIn("--cap-drop=ALL", run)
        self.assertIn("--pull=never", run)
        self.assertNotRegex(run, r":[zZ]\b")

    def test_the_cache_is_kept_apart_from_both_trees(self):
        checks = "\n".join(self.tasks["Validate import inputs"]["ansible.builtin.assert"]["that"])
        self.assertIn("homedrive_import_cache_dir ~ '/').find(homedrive_import_src", checks)
        self.assertIn("homedrive_import_cache_dir ~ '/').find(homedrive_import_store", checks)

    def test_old_versions_are_not_imported(self):
        """The user chose not to bring old versions across (2026-11-03)."""
        self.assertNotIn("--versions", self.facts["homedrive_import_args"])
        self.assertNotIn("--versions", self.tasks["Import the missing files"]["ansible.builtin.shell"]["cmd"])

    def test_read_only_steps_run_in_check_mode(self):
        for name in (
            "Read the running homedrive container's image",
            "Find what the drive lacks (read-only, by size)",
            "Check nothing is missing now (by size)",
            "Compare every source file byte for byte",
            "Check every version reads back",
            "Show what garbage collection would free",
        ):
            with self.subTest(task=name):
                self.assertIs(self.tasks[name]["check_mode"], False)
        self.assertNotIn("check_mode", self.tasks["Import the missing files"])

    def test_each_run_ends_requiring_its_checks_clean(self):
        self.assertEqual(self.names[-1], "Require a clean verify-tree and fsck")
        self.assertIn("full", self.tasks[self.names[-1]]["tags"])
        self.assertIn("Require every source path in the drive", self.names)


def _first_assert(role: str) -> list[str]:
    """The conditions of the assert a role opens with."""
    task = next(t for t in role_tasks(role) if "ansible.builtin.assert" in t)
    return task["ansible.builtin.assert"]["that"]


class ReviewedDifferencesTests(unittest.TestCase):
    """homedrive_import_accepted: reviewed differences, from the inventory."""

    def setUp(self):
        self.play = yaml.safe_load((REPO_ROOT / "homedrive_import.yml").read_text(encoding="utf-8"))[0]
        self.tasks = {t["name"]: t for t in self.play["tasks"]}
        self.text = (REPO_ROOT / "homedrive_import.yml").read_text(encoding="utf-8")

    def test_defaults_do_not_shadow_the_inventory(self):
        """Play vars beat inventory vars, so the play may not set these as vars."""
        self.assertNotIn("vars", self.play)
        facts = self.tasks["Apply the defaults for what the inventory leaves unset"]["ansible.builtin.set_fact"]
        for name, value in facts.items():
            with self.subTest(var=name):
                self.assertIn(f"{name} | default(", str(value))

    def test_the_list_is_empty_here_and_never_shown(self):
        """It names files, so it lives in the inventory and stays out of logs."""
        defaults = self.tasks["Apply the defaults for what the inventory leaves unset"]
        self.assertIn("homedrive_import_accepted | default('')", defaults["ansible.builtin.set_fact"]["homedrive_import_accepted"])
        for name in ("Validate import inputs", "Write the reviewed differences for the check"):
            with self.subTest(task=name):
                self.assertIs(self.tasks[name]["no_log"], True)
        self.assertIs(self.tasks["Write the reviewed differences for the check"]["diff"], False)

    def test_the_file_the_check_reads_is_private_and_never_left_stale(self):
        write = self.tasks["Write the reviewed differences for the check"]
        self.assertEqual(write["ansible.builtin.copy"]["mode"], "0400")
        self.assertIn("accepted.sha256", write["ansible.builtin.copy"]["dest"])
        remove = self.tasks["Remove an earlier list of reviewed differences"]
        self.assertEqual(remove["ansible.builtin.file"]["state"], "absent")
        self.assertIn("length == 0", remove["when"], "an empty variable must not leave the old list in force")

    def test_every_verify_command_reads_it_and_only_when_it_is_set(self):
        arg = self.tasks["Set the one-off container command"]["ansible.builtin.set_fact"][
            "homedrive_import_accepted_arg"
        ]
        self.assertIn("--accepted /mnt/cache/accepted.sha256", arg)
        self.assertIn("length > 0", arg)
        verifies = [
            t["ansible.builtin.shell"]["cmd"]
            for t in self.play["tasks"]
            if "verify-tree" in str(t.get("ansible.builtin.shell", {}).get("cmd", ""))
        ]
        self.assertEqual(len(verifies), 3)
        for cmd in verifies:
            self.assertIn("{{ homedrive_import_accepted_arg }}", cmd)

    def test_a_server_too_old_to_read_the_list_is_refused(self):
        """An older server ignores the flag, which would look like an empty list."""
        require = self.tasks["Require homedrive 0.1.8 or later for the reviewed list"]
        self.assertIn("is version('0.1.8', '>=')", require["ansible.builtin.assert"]["that"][0])
        self.assertIn("length > 0", require["when"])

    def test_no_reviewed_list_is_committed_here(self):
        """sha256sum-format lines name files; only the inventory may hold them."""
        pattern = re.compile(r"^\s*\\?[0-9a-f]{64}  \S", re.MULTILINE)
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout.splitlines()
        for name in tracked:
            if name.startswith("tests/") or not (REPO_ROOT / name).is_file():
                continue
            try:
                text = (REPO_ROOT / name).read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            with self.subTest(file=name):
                self.assertIsNone(pattern.search(text), f"{name} holds a sha256sum-format list")


class BackupDestinationTests(unittest.TestCase):
    """Every VM1 backup goes to homedrive."""

    def test_the_homedrive_remote_is_written_only_when_configured(self):
        config = (
            REPO_ROOT / "roles" / "standard_rclone" / "templates" / "rclone_config.j2"
        ).read_text(encoding="utf-8")
        section = config[config.index("{% if homedrive_webdav_url"):]
        self.assertIn("homedrive_rclone_pass | default('') | length > 0", section.splitlines()[0])
        self.assertIn("[Homedrive]", section)
        self.assertIn("vendor = other", section, "vendor nextcloud uses upload endpoints homedrive lacks")
        self.assertTrue(section.rstrip().endswith("{% endif %}"))

    def test_every_daily_backup_refuses_homedrive_without_a_drive(self):
        for role in ("vaultwarden", "playbook_runner", "music_server"):
            with self.subTest(role=role):
                conditions = "\n".join(_first_assert(role))
                self.assertIn("homedrive_enabled | default(false) | bool", conditions)
                self.assertIn("homedrive_backup_user in (homedrive_users", conditions)

    def test_the_homedrive_remote_defaults_to_homedrives_address(self):
        rclone = yaml.safe_load(
            (REPO_ROOT / "roles" / "standard_rclone" / "defaults" / "main.yml").read_text(encoding="utf-8")
        )
        self.assertIn("'https://drive.' ~ homelab_internal_domain", rclone["homedrive_webdav_url"])
        self.assertEqual(rclone["homedrive_rclone_pass"], "", "a secret has no default")


class RunBackupsTests(unittest.TestCase):
    """run_backups.yml takes a fresh backup now, the way the nightly jobs do."""

    def setUp(self):
        self.play = yaml.safe_load((REPO_ROOT / "run_backups.yml").read_text(encoding="utf-8"))[0]
        self.imports = [t for t in self.play["tasks"] if "ansible.builtin.import_tasks" in t]
        self.tasks = yaml.safe_load(
            (REPO_ROOT / "standalone_tasks" / "run_backup.yml").read_text(encoding="utf-8")
        )

    def test_it_is_never_part_of_the_weekly_chain(self):
        for playbook in ("vm1.yml", "homelab_vms.yml", "update_homelab_vms.yml"):
            with self.subTest(playbook=playbook):
                self.assertNotIn("run_backups", (REPO_ROOT / playbook).read_text(encoding="utf-8"))

    def test_it_runs_exactly_the_scripts_the_nightly_cron_runs(self):
        """A backup the play runs and the crontab does not would be a new kind of job.
        The restore drill is the one exception, run only when asked for."""
        crons = set()
        for path in (REPO_ROOT / "roles").glob("*/tasks/main.yml"):
            for task in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
                job = task.get("ansible.builtin.cron", {}).get("job", "")
                if "/usr/local/bin/backup_" in job:
                    crons.add(job.split()[-1])
        scripts = {
            t["vars"]["run_backup_script"]
            for t in self.imports
            if t["vars"].get("run_backup_scheduled_by", "cron") == "cron"
        }
        self.assertEqual(scripts, crons)

    def test_the_drills_run_only_when_asked_for(self):
        """The full one takes hours of disk and CPU."""
        drills = {t["vars"]["run_backup_name"]: t for t in self.imports if "drill" in t["vars"]["run_backup_name"]}
        self.assertEqual(set(drills), {"drill_light", "drill_full"})
        for name, task in drills.items():
            with self.subTest(drill=name):
                self.assertEqual(task["tags"], ["never", name])
                self.assertEqual(task["vars"]["run_backup_scheduled_by"], "installed")
                self.assertEqual(task["vars"]["run_backup_script"], "/usr/local/bin/homedrive_restore_drill.sh")
        self.assertEqual(drills["drill_light"]["vars"]["run_backup_args"], "--light")
        self.assertNotIn("run_backup_args", drills["drill_full"]["vars"])

    def test_each_backup_has_its_own_tag_and_the_store_comes_after_the_others(self):
        names = [t["vars"]["run_backup_name"] for t in self.imports]
        for task in self.imports:
            self.assertEqual(task["tags"][-1], task["vars"]["run_backup_name"])
        self.assertGreater(names.index("homedrive"), names.index("vaultwarden"))
        self.assertGreater(names.index("homedrive"), names.index("music_server"))

    def test_only_scheduled_backups_run_and_never_two_at_once(self):
        run = next(t for t in self.tasks if t["name"].startswith("Run the"))
        self.assertEqual(run["when"], "run_backup_scheduled.rc == 0")
        self.assertIn("/usr/bin/flock --nonblock", run["ansible.builtin.shell"]["cmd"])
        check = next(t for t in self.tasks if t["name"].startswith("Check"))
        self.assertIs(check["check_mode"], False)

    def test_a_failed_backup_fails_the_run(self):
        last = self.play["tasks"][-1]
        self.assertIn("always", last["tags"])
        self.assertIn("'^FAILED'", "\n".join(last["ansible.builtin.assert"]["that"]))


class SharedBorgRepositoryTests(unittest.TestCase):
    """homedrive's store backup uses the backup disk's Borg repository, which
    may still hold archives of an older job that it must never touch."""

    def read(self, *parts):
        return (REPO_ROOT.joinpath(*parts)).read_text(encoding="utf-8")

    def test_each_job_prunes_only_its_own_archives(self):
        homedrive = self.read("roles", "homedrive", "templates", "backup_homedrive.sh.j2")
        prune = homedrive[homedrive.index("borg prune"):homedrive.index('"$REPO"', homedrive.index("borg prune"))]
        self.assertIn("--glob-archives 'homedrive-*'", prune)
        self.assertIn('archive="homedrive-', homedrive)

    def test_the_drill_restores_a_homedrive_archive(self):
        drill = self.read("roles", "homedrive", "templates", "homedrive_restore_drill.sh.j2")
        line = next(l for l in drill.splitlines() if "--last 1" in l)
        self.assertIn("--glob-archives 'homedrive-*'", line)

    def test_every_borg_step_waits_for_the_lock(self):
        script = self.read("roles", "homedrive", "templates", "backup_homedrive.sh.j2")
        for line in script.splitlines():
            if re.search(r"/usr/bin/borg (create|prune|compact)", line):
                with self.subTest(line=line.strip()):
                    self.assertIn("--lock-wait", line)

    def test_the_drill_scratch_folder_is_never_inside_the_shared_repository(self):
        """Beside the backup disk's mount it would be the system disk's root."""
        defaults = yaml.safe_load(self.read("roles", "homedrive", "defaults", "main.yml"))
        self.assertIn("homedrive_borg_repo != (borg_backup_path", defaults["homedrive_drill_path"])
        self.assertIn("data_disk_mount_path | default('/data_drive')) ~ '/homedrive-drill'", defaults["homedrive_drill_path"])
        self.assertNotIn("/var/lib", defaults["homedrive_drill_path"])
        self.assertIn("backup_disk | default('') | length > 0", defaults["homedrive_borg_repo"])

    def test_no_drill_runs_on_a_schedule(self):
        """A full drill is hours of disk and CPU; drills run only when asked."""
        backup = self.read("roles", "homedrive", "templates", "backup_homedrive.sh.j2")
        self.assertNotIn("homedrive_restore_drill.sh ||", backup)
        self.assertNotIn("/usr/local/bin/homedrive_restore_drill.sh", backup)
        for path in (REPO_ROOT / "roles").glob("*/tasks/main.yml"):
            for task in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
                job = task.get("ansible.builtin.cron", {}).get("job", "")
                with self.subTest(task=task.get("name")):
                    self.assertNotIn("restore_drill", job)

    def test_the_light_drill_extracts_only_what_the_sample_needs(self):
        drill = self.read("roles", "homedrive", "templates", "homedrive_restore_drill.sh.j2")
        self.assertIn('"$IN_ARCHIVE/store.id" "$IN_ARCHIVE/meta"', drill)
        self.assertIn('on_copy drill-plan --sample "$SAMPLE" --seed "$SEED"', drill)
        self.assertIn('on_copy restore-drill --to /restore --sample "$SAMPLE" --seed "$SEED"', drill)
        self.assertIn('COMPARE=(--sample)', drill)


class MusicLibraryTests(unittest.TestCase):
    """music-server plays homedrive's Music export once homedrive is deployed."""

    def test_the_library_follows_homedrive_and_stays_read_only(self):
        defaults = yaml.safe_load(
            (REPO_ROOT / "roles" / "music_server" / "defaults" / "main.yml").read_text(encoding="utf-8")
        )
        self.assertEqual(
            defaults["music_server_library"],
            "{{ 'homedrive' if homedrive_enabled | default(false) | bool else 'path' }}",
        )
        script = (REPO_ROOT / "roles" / "music_server" / "templates" / "music_server.sh.j2").read_text(
            encoding="utf-8"
        )
        self.assertIn("{{ music_server_library_path | default(music_server_music_path) }}:/music:ro,z", script)

    def test_the_export_folder_exists_before_music_server_mounts_it(self):
        names = [t.get("name") for t in role_tasks("music_server")]
        self.assertLess(
            names.index("Create the homedrive Music export folder"),
            names.index(next(n for n in names if n and n.startswith("Start music-server"))),
        )

    def test_homedrive_exports_music_for_an_account_it_has(self):
        defaults = yaml.safe_load(
            (REPO_ROOT / "roles" / "homedrive" / "defaults" / "main.yml").read_text(encoding="utf-8")
        )
        self.assertIn(":Music=>music", defaults["homedrive_exports"])
        conditions = "\n".join(_first_assert("homedrive"))
        self.assertIn("difference(homedrive_users | map(attribute='name') | list)", conditions)


class BackupScheduleTests(unittest.TestCase):
    """The nightly jobs are staggered so each holds what came before it."""

    def when(self, role, prefix):
        defaults = yaml.safe_load(
            (REPO_ROOT / "roles" / role / "defaults" / "main.yml").read_text(encoding="utf-8")
        )
        return int(defaults[f"{prefix}_hour"]) * 60 + int(defaults[f"{prefix}_minute"])

    def test_the_store_is_archived_after_the_backups_that_land_in_it(self):
        store = self.when("homedrive", "homedrive_backup")
        for role, prefix in (
            ("vaultwarden", "vaultwarden_backup"),
            ("playbook_runner", "playbook_runner_backup"),
            ("music_server", "music_server_backup"),
        ):
            with self.subTest(job=prefix):
                self.assertLess(self.when(role, prefix), store)

    def test_every_backup_cron_entry_uses_its_schedule_variables(self):
        for path in (REPO_ROOT / "roles").glob("*/tasks/main.yml"):
            for task in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
                cron = task.get("ansible.builtin.cron", {})
                if "/usr/local/bin/backup_" not in cron.get("job", ""):
                    continue
                with self.subTest(job=cron["job"]):
                    self.assertNotIn("special_time", cron)
                    self.assertRegex(cron["hour"], r"^\{\{ \w+_hour \}\}$")
                    self.assertRegex(cron["minute"], r"^\{\{ \w+_minute \}\}$")

    def test_show_logs_reads_the_backups_without_changing_anything(self):
        play = yaml.safe_load((REPO_ROOT / "show_logs.yml").read_text(encoding="utf-8"))[0]
        task = next(t for t in play["tasks"] if t["name"] == "Read the backups")
        self.assertIs(task["check_mode"], False)
        self.assertIs(task["changed_when"], False)
        self.assertEqual(task["tags"], ["backups"])

    def test_a_second_borg_run_on_one_day_makes_a_new_archive(self):
        """run_backups.yml can run a job again the day the cron job has."""
        for parts in (("roles", "homedrive", "templates", "backup_homedrive.sh.j2"),):
            text = (REPO_ROOT.joinpath(*parts)).read_text(encoding="utf-8")
            with self.subTest(script=parts[-1]):
                self.assertRegex(text, r"(archive|ARCHIVE)=.*%H%M%S")

