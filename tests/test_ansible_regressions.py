from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


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
