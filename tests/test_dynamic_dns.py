import os
import logging
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "roles" / "dynamic_dns" / "templates" / "dynamic_dns.py.j2"


def load_module():
    module = types.ModuleType("dynamic_dns_under_test")
    environment = {
        "PORKBUN_API_KEY": "test-key",
        "PORKBUN_SECRET_KEY": "test-secret",
        "DOMAIN": "example.com",
        "SUBDOMAIN": "home",
    }
    with (
        mock.patch.dict(os.environ, environment, clear=False),
        mock.patch("logging.handlers.RotatingFileHandler", return_value=logging.NullHandler()),
    ):
        exec(compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), module.__dict__)
    return module


class DynamicDnsTests(unittest.TestCase):
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

    def test_update_uses_edit_or_create_endpoint(self):
        module = load_module()
        module._porkbun_post = mock.Mock(return_value={"status": "SUCCESS"})
        module.update_dns_record("42", "8.8.8.8")
        self.assertIn("dns/edit/example.com/42", module._porkbun_post.call_args.args[0])
        module.update_dns_record(None, "8.8.4.4")
        self.assertIn("dns/create/example.com", module._porkbun_post.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
