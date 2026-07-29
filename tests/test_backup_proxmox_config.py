import os
from pathlib import Path
import subprocess
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "backup_proxmox_config.sh"


class ProxmoxConfigBackupTests(unittest.TestCase):
    def test_missing_destination_fails_before_backup_work(self):
        environment = os.environ.copy()
        environment.pop("RCLONE_DEST", None)

        result = subprocess.run(
            ["bash", str(SCRIPT)],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=5,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("Set RCLONE_DEST", result.stderr)

    def test_temporary_archive_is_private_and_cleaned_on_every_exit(self):
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("umask 077", script)
        self.assertIn("trap cleanup EXIT", script)
        self.assertIn('rm -rf -- "$STAGING"', script)
        self.assertNotIn('\nrm -rf "$STAGING"', script)

    def test_retention_cannot_delete_unrelated_remote_files(self):
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("--max-depth 1", script)
        self.assertIn("--include 'proxmox_config_*.tar.gz'", script)
        self.assertNotIn('rclone delete --min-age 30d "$RCLONE_DEST"', script)


if __name__ == "__main__":
    unittest.main()
