import json
import tomllib
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_DIR = REPO_ROOT / "roles" / "dev_vm" / "files"


class DevVmPrivacyPolicyTests(unittest.TestCase):
    def load_toml(self, name):
        with (POLICY_DIR / name).open("rb") as policy_file:
            return tomllib.load(policy_file)

    def load_json(self, name):
        with (POLICY_DIR / name).open(encoding="utf-8") as policy_file:
            return json.load(policy_file)

    def test_codex_disables_all_client_telemetry(self):
        config = self.load_toml("codex-managed-config.toml")

        self.assertFalse(config["analytics"]["enabled"])
        self.assertFalse(config["feedback"]["enabled"])
        self.assertEqual(config["otel"]["exporter"], "none")
        self.assertEqual(config["otel"]["metrics_exporter"], "none")
        self.assertEqual(config["otel"]["trace_exporter"], "none")
        self.assertFalse(config["otel"]["log_user_prompt"])

    def test_codex_disables_non_model_cloud_sharing(self):
        requirements = self.load_toml("codex-requirements.toml")

        self.assertFalse(requirements["allow_appshots"])
        self.assertFalse(requirements["allow_remote_control"])
        self.assertNotIn("features", requirements)

    def test_claude_disables_separable_telemetry_and_cloud_sharing(self):
        settings = self.load_json("claude-managed-settings.json")
        environment = settings["env"]

        self.assertTrue(settings["disableArtifact"])
        self.assertTrue(settings["disableRemoteControl"])
        for variable in (
            "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY",
            "DISABLE_ERROR_REPORTING",
            "DISABLE_FEEDBACK_COMMAND",
            "DO_NOT_TRACK",
        ):
            self.assertEqual(environment[variable], "1")

        self.assertEqual(environment["CLAUDE_CODE_ENABLE_TELEMETRY"], "0")
        for exporter in (
            "OTEL_LOGS_EXPORTER",
            "OTEL_METRICS_EXPORTER",
            "OTEL_TRACES_EXPORTER",
        ):
            self.assertEqual(environment[exporter], "none")

    def test_capability_affecting_controls_remain_enabled(self):
        environment = self.load_json("claude-managed-settings.json")["env"]

        for variable in (
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
            "DISABLE_AUTOUPDATER",
            "DISABLE_GROWTHBOOK",
            "DISABLE_TELEMETRY",
            "ENABLE_CLAUDEAI_MCP_SERVERS",
        ):
            self.assertNotIn(variable, environment)

    def test_balanced_policy_preserves_local_history_and_memory(self):
        codex_config = self.load_toml("codex-managed-config.toml")
        claude_environment = self.load_json("claude-managed-settings.json")["env"]

        self.assertNotIn("history", codex_config)
        self.assertNotIn("CLAUDE_CODE_SKIP_PROMPT_HISTORY", claude_environment)
        self.assertNotIn("CLAUDE_CODE_DISABLE_AUTO_MEMORY", claude_environment)
        self.assertNotIn("DISABLE_PROMPT_CACHING", claude_environment)


if __name__ == "__main__":
    unittest.main()
