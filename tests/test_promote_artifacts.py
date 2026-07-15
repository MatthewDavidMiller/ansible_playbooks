from datetime import date
import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "promote_artifacts.py"
SPEC = importlib.util.spec_from_file_location("promote_artifacts", MODULE_PATH)
promote = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = promote
SPEC.loader.exec_module(promote)


class PromotionPolicyTests(unittest.TestCase):
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
        self.assertEqual(result.critical_ids, frozenset({"CVE-2"}))

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


if __name__ == "__main__":
    unittest.main()
