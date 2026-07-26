import logging
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "roles" / "dynamic_dns" / "templates" / "dynamic_dns.py.j2"


def load_module():
    module = types.ModuleType("dynamic_dns_under_test")
    logging.getLogger("dynamic_dns").handlers.clear()
    environment = {
        "PORKBUN_API_KEY": "test-key",
        "PORKBUN_SECRET_KEY": "test-secret",
        "DOMAIN": "example.com",
        "SUBDOMAIN": "home",
    }
    with mock.patch.dict(os.environ, environment, clear=False):
        exec(compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), module.__dict__)
    return module


class DynamicDnsTests(unittest.TestCase):
    def test_logging_uses_one_non_propagating_stderr_handler(self):
        module = load_module()

        self.assertFalse(module.log.propagate)
        self.assertEqual(len(module.log.handlers), 1)
        self.assertIsInstance(module.log.handlers[0], logging.StreamHandler)

    def test_wan_ip_must_be_global_ipv4(self):
        module = load_module()
        module._porkbun_post = mock.Mock(return_value={"yourIp": "192.168.1.10"})
        with self.assertRaises(ValueError):
            module.get_wan_ip()
        module._porkbun_post.return_value = {"yourIp": "8.8.8.8"}
        self.assertEqual(module.get_wan_ip(), "8.8.8.8")

    def test_cached_ip_avoids_dns_api_calls(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            module.IP_CACHE = Path(directory) / "ip"
            module.IP_CACHE.write_text("8.8.8.8", encoding="utf-8")
            module.get_wan_ip = mock.Mock(return_value="8.8.8.8")
            module.get_dns_record = mock.Mock(side_effect=AssertionError("DNS lookup should be skipped"))
            self.assertEqual(module.main(), 0)
            module.get_dns_record.assert_not_called()

    def test_cache_read_and_atomic_write(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            module.IP_CACHE = Path(directory) / "nested" / "ip"
            self.assertIsNone(module.get_cached_ip())
            module.write_cached_ip("8.8.8.8")
            self.assertEqual(module.get_cached_ip(), "8.8.8.8")
            self.assertEqual(module.IP_CACHE.stat().st_mode & 0o777, 0o600)

    def test_porkbun_post_sends_credentials_and_handles_errors(self):
        module = load_module()
        response = mock.Mock(ok=True, status_code=200, reason="OK")
        response.json.return_value = {"status": "SUCCESS", "value": 1}
        with mock.patch.object(module.requests, "post", return_value=response) as post:
            self.assertEqual(module._porkbun_post("ping", {"extra": "value"})["value"], 1)
        self.assertEqual(post.call_args.kwargs["timeout"], module.TIMEOUT)
        self.assertEqual(post.call_args.kwargs["json"]["apikey"], "test-key")
        self.assertEqual(post.call_args.kwargs["json"]["extra"], "value")

        response.ok = False
        response.status_code = 503
        response.reason = "Unavailable"
        response.json.return_value = {"code": "X", "message": "retry"}
        with mock.patch.object(module.requests, "post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "HTTP 503.*retry"):
                module._porkbun_post("ping", {})

        response.ok = True
        response.json.return_value = {"status": "ERROR", "message": "denied"}
        with mock.patch.object(module.requests, "post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "returned status.*denied"):
                module._porkbun_post("ping", {})

    def test_porkbun_post_rejects_non_json_success(self):
        module = load_module()
        response = mock.Mock(ok=True, status_code=200, reason="OK")
        response.json.side_effect = ValueError("not json")
        with mock.patch.object(module.requests, "post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "returned status"):
                module._porkbun_post("ping", {})

    def test_dns_record_cardinality(self):
        module = load_module()
        module._porkbun_post = mock.Mock(return_value={"records": []})
        self.assertEqual(module.get_dns_record(), (None, None))
        module._porkbun_post.return_value = {
            "records": [{"content": "8.8.8.8", "id": "42"}]
        }
        self.assertEqual(module.get_dns_record(), ("8.8.8.8", "42"))
        module._porkbun_post.return_value = {"records": [{}, {}]}
        with self.assertRaisesRegex(RuntimeError, "Expected one"):
            module.get_dns_record()
        module._porkbun_post.return_value = {"records": {"content": "8.8.8.8"}}
        with self.assertRaisesRegex(RuntimeError, "invalid records list"):
            module.get_dns_record()

    def test_dns_record_rejects_missing_or_malformed_fields(self):
        module = load_module()
        for record in (
            {"content": "8.8.8.8"},
            {"content": "8.8.8.8", "id": "not-numeric"},
            {"content": "not-an-ip", "id": "42"},
            {"content": "2001:4860:4860::8888", "id": "42"},
        ):
            with self.subTest(record=record):
                module._porkbun_post = mock.Mock(return_value={"records": [record]})
                with self.assertRaisesRegex(RuntimeError, "invalid"):
                    module.get_dns_record()

    def test_main_reconciles_cache_without_unneeded_update(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            module.IP_CACHE = Path(directory) / "ip"
            module.get_wan_ip = mock.Mock(return_value="8.8.8.8")
            module.get_dns_record = mock.Mock(return_value=("8.8.8.8", "42"))
            module.update_dns_record = mock.Mock()
            self.assertEqual(module.main(), 0)
            self.assertEqual(module.IP_CACHE.read_text(encoding="utf-8"), "8.8.8.8")
            module.update_dns_record.assert_not_called()

    def test_main_returns_failure_for_each_api_stage(self):
        module = load_module()
        module.log = mock.Mock()
        module.get_wan_ip = mock.Mock(side_effect=RuntimeError("ping failed"))
        self.assertEqual(module.main(), 1)

        module = load_module()
        module.log = mock.Mock()
        module.get_wan_ip = mock.Mock(return_value="8.8.8.8")
        module.get_cached_ip = mock.Mock(return_value=None)
        module.get_dns_record = mock.Mock(side_effect=RuntimeError("lookup failed"))
        self.assertEqual(module.main(), 1)

        module = load_module()
        module.log = mock.Mock()
        module.get_wan_ip = mock.Mock(return_value="8.8.8.8")
        module.get_cached_ip = mock.Mock(return_value=None)
        module.get_dns_record = mock.Mock(return_value=("8.8.4.4", "42"))
        module.update_dns_record = mock.Mock(side_effect=RuntimeError("update failed"))
        self.assertEqual(module.main(), 1)

    def test_main_updates_record_and_cache(self):
        module = load_module()
        module.log = mock.Mock()
        with tempfile.TemporaryDirectory() as directory:
            module.IP_CACHE = Path(directory) / "ip"
            module.get_wan_ip = mock.Mock(return_value="8.8.8.8")
            module.get_dns_record = mock.Mock(return_value=("8.8.4.4", "42"))
            module.update_dns_record = mock.Mock()
            self.assertEqual(module.main(), 0)
            module.update_dns_record.assert_called_once_with("42", "8.8.8.8")
            self.assertEqual(module.get_cached_ip(), "8.8.8.8")

    def test_main_reports_cache_read_and_write_failures(self):
        module = load_module()
        module.log = mock.Mock()
        module.get_wan_ip = mock.Mock(return_value="8.8.8.8")
        module.get_cached_ip = mock.Mock(side_effect=PermissionError("denied"))
        self.assertEqual(module.main(), 1)
        module.log.error.assert_called_once()

        module = load_module()
        module.log = mock.Mock()
        module.get_wan_ip = mock.Mock(return_value="8.8.8.8")
        module.get_cached_ip = mock.Mock(return_value=None)
        module.get_dns_record = mock.Mock(return_value=("8.8.8.8", "42"))
        module.write_cached_ip = mock.Mock(side_effect=PermissionError("denied"))
        self.assertEqual(module.main(), 1)
        module.log.error.assert_called_once()

    def test_update_uses_edit_or_create_endpoint(self):
        module = load_module()
        module._porkbun_post = mock.Mock(return_value={"status": "SUCCESS"})
        module.update_dns_record("42", "8.8.8.8")
        self.assertIn("dns/edit/example.com/42", module._porkbun_post.call_args.args[0])
        module.update_dns_record(None, "8.8.4.4")
        self.assertIn("dns/create/example.com", module._porkbun_post.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
