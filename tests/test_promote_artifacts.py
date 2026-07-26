from datetime import date, datetime, timedelta, timezone
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "promote_artifacts.py"
SPEC = importlib.util.spec_from_file_location("promote_artifacts", MODULE_PATH)
promote = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = promote
SPEC.loader.exec_module(promote)


class ToolResolutionTests(unittest.TestCase):
    def setUp(self):
        promote.resolve_tool_command.cache_clear()
        self.addCleanup(promote.resolve_tool_command.cache_clear)

    def test_tool_lookup_is_cached_across_services(self):
        """Every service needs the same three tools; probing PATH and the
        container engines once per service wastes a run's worth of syscalls."""
        with mock.patch.object(
            promote.shutil, "which", return_value="/usr/bin/skopeo"
        ) as which:
            for _ in range(5):
                self.assertEqual(promote.tool_command("skopeo"), ["/usr/bin/skopeo"])
        which.assert_called_once_with("skopeo")

    def test_cached_command_cannot_be_mutated_by_a_caller(self):
        with mock.patch.object(promote.shutil, "which", return_value="/usr/bin/trivy"):
            first = promote.tool_command("trivy")
            first.append("--corrupted")
            self.assertEqual(promote.tool_command("trivy"), ["/usr/bin/trivy"])

    def test_missing_tool_without_container_engine_fails_closed(self):
        with (
            mock.patch.object(promote.shutil, "which", return_value=None),
            mock.patch.object(promote, "container_engine", return_value=None),
        ):
            with self.assertRaises(SystemExit):
                promote.resolve_tool_command("cosign")


class PromotionPolicyTests(unittest.TestCase):
    def test_lock_file_write_is_atomic_and_preserves_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock.yml"
            path.write_text("old: value\n", encoding="utf-8")
            path.chmod(0o640)
            real_replace = os.replace
            replaced_payload = None

            def observe_replace(source, destination):
                nonlocal replaced_payload
                replaced_payload = Path(source).read_text(encoding="utf-8")
                real_replace(source, destination)

            with mock.patch.object(promote.os, "replace", side_effect=observe_replace) as replace:
                promote.write_lock_file(path, {"artifact_locked_images": {}})

            replace.assert_called_once()
            self.assertEqual(path.read_text(encoding="utf-8"), replaced_payload)
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_lock_file_write_keeps_original_and_cleans_temp_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock.yml"
            path.write_text("old: value\n", encoding="utf-8")

            with mock.patch.object(
                promote.yaml, "safe_dump", side_effect=OSError("disk full")
            ):
                with self.assertRaisesRegex(OSError, "disk full"):
                    promote.write_lock_file(path, {"artifact_locked_images": {}})

            self.assertEqual(path.read_text(encoding="utf-8"), "old: value\n")
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_digest_validation_requires_lowercase_hex(self):
        digest = "sha256:" + "a" * 64
        self.assertEqual(promote.validate_digest(digest, "digest"), digest)
        for invalid in ("sha256:" + "g" * 64, "sha256:" + "A" * 64, "sha256:abc", 1):
            with self.subTest(invalid=invalid):
                with self.assertRaises(SystemExit):
                    promote.validate_digest(invalid, "digest")

    def test_lock_entry_requires_expected_shape(self):
        valid = {
            "upstream_ref": "registry.example/app:1",
            "internal_repo": "homelab/app",
            "approved_digest": "sha256:" + "a" * 64,
            "signature_required": False,
        }
        self.assertIs(promote.validate_lock_entry(valid, "app"), valid)
        for invalid in (None, {}, {**valid, "approved_digest": "sha256:bad"}, {**valid, "signature_required": "false"}):
            with self.subTest(invalid=invalid):
                with self.assertRaises(SystemExit):
                    promote.validate_lock_entry(invalid, "app")

    def test_exception_metadata_is_time_bounded(self):
        entry = {
            "vulnerability_exception": promote.NO_NEWER_IMAGE_EXCEPTION,
            "vulnerability_exception_reviewed_on": "2026-07-14",
            "vulnerability_exception_expires_on": "2026-08-13",
        }
        promote.validate_exception_metadata(entry, "service", today=date(2026, 7, 14))
        entry["vulnerability_exception_expires_on"] = "2026-08-14"
        with self.assertRaises(SystemExit):
            promote.validate_exception_metadata(entry, "service", today=date(2026, 7, 14))

    def test_expired_exception_is_rejected(self):
        entry = {
            "vulnerability_exception": promote.NO_NEWER_IMAGE_EXCEPTION,
            "vulnerability_exception_reviewed_on": "2026-06-01",
            "vulnerability_exception_expires_on": "2026-07-01",
        }
        with self.assertRaises(SystemExit):
            promote.validate_exception_metadata(entry, "service", today=date(2026, 7, 14))

    def test_trivy_json_distinguishes_critical_findings(self):
        report = {
            "Results": [{"Vulnerabilities": [
                {"VulnerabilityID": "CVE-1", "Severity": "HIGH"},
                {"VulnerabilityID": "CVE-2", "Severity": "CRITICAL"},
            ]}]
        }
        result = promote.parse_trivy_result(json.dumps(report), "service")
        self.assertEqual(result.finding_count, 2)
        self.assertEqual(result.non_critical_count, 1)
        self.assertEqual(result.critical_ids, frozenset({"CVE-2"}))

    def test_changed_image_must_be_at_least_24_hours_old(self):
        created = datetime(2026, 7, 13, 6, 52, tzinfo=timezone.utc)
        promote.validate_minimum_image_age(
            created,
            "service",
            now=created + timedelta(hours=promote.MINIMUM_IMAGE_AGE_HOURS),
        )
        with self.assertRaises(SystemExit):
            promote.validate_minimum_image_age(
                created,
                "service",
                now=created + timedelta(hours=promote.MINIMUM_IMAGE_AGE_HOURS, seconds=-1),
            )

    def test_preexisting_critical_findings_are_not_a_regression(self):
        current = promote.ScanResult(3, 1, frozenset({"CVE-1", "CVE-2"}))
        self.assertTrue(promote.critical_findings_are_preexisting(["CVE-1", "CVE-2"], current))
        self.assertFalse(promote.critical_findings_are_preexisting(["CVE-1", "CVE-3"], current))
        self.assertFalse(promote.critical_findings_are_preexisting(["CVE-1"], None))

    def test_critical_acceptance_is_exact_and_expires_within_30_days(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acceptance.yml"
            path.write_text(
                "accepted_critical_vulnerabilities:\n"
                "  - service: app\n"
                f"    image_digest: sha256:{'a' * 64}\n"
                "    vulnerability_id: CVE-1\n"
                "    reason: No fixed image.\n"
                "    compensating_controls:\n"
                "      - Not reachable.\n"
                "    expires_on: '2026-08-13'\n",
                encoding="utf-8",
            )
            accepted = promote.load_critical_acceptances(path, today=date(2026, 7, 14))
            self.assertIn(("app", "sha256:" + "a" * 64, "CVE-1"), accepted)

            path.write_text(path.read_text(encoding="utf-8").replace("a" * 64, "g" * 64), encoding="utf-8")
            with self.assertRaises(SystemExit):
                promote.load_critical_acceptances(path, today=date(2026, 7, 14))

    def test_image_inspection_parses_digest_and_utc_creation_time(self):
        result = mock.Mock(stdout=json.dumps({
            "Digest": "sha256:" + "a" * 64,
            "Created": "2026-07-01T12:00:00-04:00",
        }))
        with (
            mock.patch.object(promote, "run", return_value=result),
            mock.patch.object(promote, "tool_command", return_value=["skopeo"]),
        ):
            inspection = promote.inspect_image("registry.example/app:1")
        self.assertEqual(inspection.digest, "sha256:" + "a" * 64)
        self.assertEqual(inspection.created, datetime(2026, 7, 1, 16, tzinfo=timezone.utc))

    def test_image_inspection_rejects_malformed_metadata(self):
        for output in ("not-json", "[]", json.dumps({"Digest": "sha256:bad"})):
            with self.subTest(output=output):
                with (
                    mock.patch.object(promote, "run", return_value=mock.Mock(stdout=output)),
                    mock.patch.object(promote, "tool_command", return_value=["skopeo"]),
                ):
                    with self.assertRaises(SystemExit):
                        promote.inspect_image("registry.example/app:1")

    def test_trivy_json_rejects_malformed_report_shapes(self):
        for report in ([], {"Results": {}}, {"Results": [None]}, {"Results": [{"Vulnerabilities": {}}]}):
            with self.subTest(report=report):
                with self.assertRaises(SystemExit):
                    promote.parse_trivy_result(json.dumps(report), "service")

    def test_signature_arguments_require_one_identity_and_issuer(self):
        entry = {
            "signature_identity": "https://example.test/workflow",
            "signature_oidc_issuer": "https://issuer.test",
        }
        self.assertEqual(
            promote.signature_verification_args(entry, "app"),
            [
                "--certificate-identity",
                entry["signature_identity"],
                "--certificate-oidc-issuer",
                entry["signature_oidc_issuer"],
            ],
        )
        with self.assertRaises(SystemExit):
            promote.signature_verification_args({}, "app")
        with self.assertRaises(SystemExit):
            promote.signature_verification_args(
                {**entry, "signature_identity_regexp": ".*"}, "app"
            )

    def test_digest_reference_replaces_tag_or_existing_digest(self):
        digest = "sha256:" + "b" * 64
        self.assertEqual(
            promote.to_digest_ref("registry.example:5000/app:1.2", digest),
            f"registry.example:5000/app@{digest}",
        )
        self.assertEqual(
            promote.to_digest_ref("registry.example/app@sha256:" + "a" * 64, digest),
            f"registry.example/app@{digest}",
        )

    def test_main_inspects_each_selected_image_once(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_file = Path(directory) / "lock.yml"
            lock_file.write_text(
                "artifact_locked_images:\n"
                "  app:\n"
                "    upstream_ref: registry.example/app:1\n"
                "    internal_repo: homelab/app\n"
                f"    approved_digest: sha256:{'a' * 64}\n"
                "    signature_required: false\n",
                encoding="utf-8",
            )
            inspection = promote.ImageInspection("sha256:" + "a" * 64, None)
            argv = [
                "promote_artifacts.py",
                "--lock-file",
                str(lock_file),
                "--service",
                "app",
                "--skip-scan",
                "--skip-signature-verify",
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(promote, "resolve_tool_command", return_value=(["skopeo"], "local")),
                mock.patch.object(promote, "inspect_image", return_value=inspection) as inspect,
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(promote.main(), 0)
            inspect.assert_called_once_with("registry.example/app:1")


if __name__ == "__main__":
    unittest.main()
