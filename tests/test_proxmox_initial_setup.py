import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "proxmox_initial_setup.py"
SPEC = importlib.util.spec_from_file_location("proxmox_initial_setup", MODULE_PATH)
proxmox = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = proxmox
SPEC.loader.exec_module(proxmox)


class ProxmoxParsingTests(unittest.TestCase):
    def test_parse_qm_config_ignores_unstructured_lines(self):
        parsed = proxmox.parse_qm_config("name: VM2\nscsi0: local-lvm:vm-121-disk-0,size=32G\nnoise\n")
        self.assertEqual(parsed["name"], "VM2")
        self.assertNotIn("noise", parsed)

    def test_size_parsing_and_disk_extraction(self):
        self.assertEqual(proxmox.parse_size_bytes("1.5G"), int(1.5 * 1024**3))
        self.assertEqual(
            proxmox.disk_size_bytes("scsi0: local-lvm:vm-1-disk-0,size=100G", "scsi0"),
            100 * 1024**3,
        )
        with self.assertRaises(ValueError):
            proxmox.parse_size_bytes("100GB")


if __name__ == "__main__":
    unittest.main()
