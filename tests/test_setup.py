import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "setup.py"
SPEC = importlib.util.spec_from_file_location("setup_under_test", MODULE_PATH)
setup = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = setup
SPEC.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def test_main_installs_packages_and_secures_config_directory(self):
        root_user = mock.Mock(pw_uid=0, pw_gid=0)
        with (
            mock.patch.object(setup, "run") as run,
            mock.patch.object(setup, "Path") as path,
            mock.patch.object(setup.pwd, "getpwnam", return_value=root_user),
            mock.patch.object(setup.os, "chown") as chown,
            mock.patch.object(setup.os, "chmod") as chmod,
        ):
            directory = path.return_value
            self.assertEqual(setup.main(), 0)

        run.assert_called_once_with(["dnf", "install", "-y", *setup.BOOTSTRAP_PACKAGES])
        path.assert_called_once_with("/ansible_configs")
        directory.mkdir.assert_called_once_with(mode=0o700, exist_ok=True)
        chown.assert_called_once_with(directory, 0, 0)
        chmod.assert_called_once_with(directory, setup.stat.S_IRWXU)

    def test_run_checks_subprocess_result(self):
        with mock.patch.object(setup.subprocess, "run") as run:
            setup.run(["command", "argument"])
        run.assert_called_once_with(["command", "argument"], check=True)


if __name__ == "__main__":
    unittest.main()
