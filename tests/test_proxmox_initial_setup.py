import importlib.util
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "proxmox_initial_setup.py"
SPEC = importlib.util.spec_from_file_location("proxmox_initial_setup", MODULE_PATH)
proxmox = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = proxmox
SPEC.loader.exec_module(proxmox)


class ProxmoxParsingTests(unittest.TestCase):
    def test_qm_config_distinguishes_absent_vms_from_query_failures(self):
        with mock.patch.object(
            proxmox,
            "capture",
            return_value=mock.Mock(returncode=0, stdout="name: VM1\n", stderr=""),
        ):
            self.assertEqual(proxmox.qm_config("120"), "name: VM1\n")

        with mock.patch.object(
            proxmox,
            "capture",
            return_value=mock.Mock(
                returncode=2,
                stdout="",
                stderr="Configuration file 'nodes/pve/qemu-server/120.conf' does not exist",
            ),
        ):
            self.assertIsNone(proxmox.qm_config("120"))

        with mock.patch.object(
            proxmox,
            "capture",
            return_value=mock.Mock(
                returncode=255,
                stdout="",
                stderr="cluster filesystem unavailable",
            ),
        ):
            with self.assertRaisesRegex(SystemExit, "cluster filesystem unavailable"):
                proxmox.qm_config("120")

    def test_parse_qm_config_ignores_unstructured_lines(self):
        parsed = proxmox.parse_qm_config("name: VM1\nscsi0: local-lvm:vm-120-disk-0,size=32G\nnoise\n")
        self.assertEqual(parsed["name"], "VM1")
        self.assertNotIn("noise", parsed)

    def test_size_parsing_and_disk_extraction(self):
        self.assertEqual(proxmox.parse_size_bytes("1.5G"), int(1.5 * 1024**3))
        self.assertEqual(
            proxmox.disk_size_bytes("scsi0: local-lvm:vm-1-disk-0,size=100G", "scsi0"),
            100 * 1024**3,
        )
        with self.assertRaises(ValueError):
            proxmox.parse_size_bytes("100GB")

    def test_managed_identity_rejects_vmid_collision(self):
        proxmox.require_managed_identity({"name": "VM1"}, "120", "VM1", "VM")
        with self.assertRaisesRegex(SystemExit, "Refusing to modify"):
            proxmox.require_managed_identity({"name": "Unrelated"}, "120", "VM1", "VM")

    def test_set_vm_options_only_applies_drift(self):
        parsed = {"name": "VM1", "cores": "2"}
        with mock.patch.object(proxmox, "run_change") as run_change:
            proxmox.set_vm_options("120", parsed, {"name": "VM1", "cores": "2"}, "Configure")
            run_change.assert_not_called()
            proxmox.set_vm_options("120", parsed, {"name": "VM1", "cores": "4"}, "Configure")
        run_change.assert_called_once_with(
            "Configure: cores=4", ["qm", "set", "120", "--cores", "4"]
        )
        self.assertEqual(parsed["cores"], "4")

    def test_cloud_image_lock_validates_url_filename_and_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock.yml"

            def write_lock(url="https://example.test/image.qcow2", filename="image.qcow2", digest="a" * 64):
                path.write_text(
                    "cloud_image_lock:\n"
                    "  rocky_linux_10_x86_64:\n"
                    f"    url: {url}\n"
                    f"    filename: {filename}\n"
                    f"    sha256: {digest}\n",
                    encoding="utf-8",
                )

            with mock.patch.object(proxmox, "resolve_lock_file", return_value=path):
                write_lock()
                self.assertEqual(proxmox.load_rocky_image_lock()["filename"], "image.qcow2")
                for kwargs in (
                    {"url": "http://example.test/image.qcow2"},
                    {"filename": "../image.qcow2"},
                    {"digest": "g" * 64},
                ):
                    with self.subTest(kwargs=kwargs):
                        write_lock(**kwargs)
                        with self.assertRaises(SystemExit):
                            proxmox.load_rocky_image_lock()

    def test_verified_download_is_atomic_and_cleans_failures(self):
        payload = b"verified image"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            with (
                mock.patch.object(proxmox, "DOWNLOAD_DIR", Path(directory)),
                mock.patch.object(proxmox.urllib.request, "urlopen", return_value=io.BytesIO(payload)) as urlopen,
                mock.patch("builtins.print"),
            ):
                destination = proxmox.download_verified_image(
                    "https://example.test/image.qcow2", "image.qcow2", digest
                )
            self.assertEqual(destination.read_bytes(), payload)
            urlopen.assert_called_once_with(
                "https://example.test/image.qcow2", timeout=proxmox.DOWNLOAD_TIMEOUT
            )

            destination.unlink()
            with (
                mock.patch.object(proxmox, "DOWNLOAD_DIR", Path(directory)),
                mock.patch.object(proxmox.urllib.request, "urlopen", return_value=io.BytesIO(payload)),
            ):
                with self.assertRaisesRegex(SystemExit, "Checksum mismatch"):
                    proxmox.download_verified_image(
                        "https://example.test/image.qcow2", "image.qcow2", "b" * 64
                    )
            self.assertFalse((Path(directory) / "image.qcow2.part").exists())

            partial = Path(directory) / "image.qcow2.part"
            partial.write_bytes(b"stale")
            with (
                mock.patch.object(proxmox, "DOWNLOAD_DIR", Path(directory)),
                mock.patch.object(
                    proxmox.urllib.request,
                    "urlopen",
                    side_effect=TimeoutError("download timed out"),
                ),
            ):
                with self.assertRaises(TimeoutError):
                    proxmox.download_verified_image(
                        "https://example.test/image.qcow2", "image.qcow2", digest
                    )
            self.assertFalse(partial.exists())

    def test_clone_refuses_to_modify_unrelated_existing_vm(self):
        vm = {"vmid": "120", "name": "VM1", "cores": "2", "memory": "1024"}
        with (
            mock.patch.object(proxmox, "qm_config", return_value="name: Unrelated\n"),
            mock.patch.object(proxmox, "run_change") as run_change,
        ):
            with self.assertRaisesRegex(SystemExit, "Refusing to modify"):
                proxmox.clone_rocky_vm(vm)
        run_change.assert_not_called()

    def test_existing_template_name_collision_is_rejected(self):
        with (
            mock.patch.object(
                proxmox,
                "qm_config",
                return_value="name: UnrelatedTemplate\ntemplate: 1\n",
            ),
            mock.patch.object(proxmox, "configure_rocky_template") as configure,
        ):
            with self.assertRaisesRegex(SystemExit, "Refusing to modify"):
                proxmox.create_rocky_template()
        configure.assert_not_called()


if __name__ == "__main__":
    unittest.main()
