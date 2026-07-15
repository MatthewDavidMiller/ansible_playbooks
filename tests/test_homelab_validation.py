import unittest

from filter_plugins.homelab_validation import (
    homelab_immutable_image,
    homelab_ip_in_network,
    homelab_safe_absolute_path,
    homelab_safe_name,
    homelab_valid_ipv4_cidr,
)


class HomelabValidationTests(unittest.TestCase):
    def test_cidr_is_semantic_and_rejects_default_route(self):
        self.assertTrue(homelab_valid_ipv4_cidr("172.16.1.0/28"))
        self.assertFalse(homelab_valid_ipv4_cidr("172.16.1.1/28"))
        self.assertFalse(homelab_valid_ipv4_cidr("0.0.0.0/0"))
        self.assertFalse(homelab_valid_ipv4_cidr("2001:db8::/64"))

    def test_static_ip_must_be_usable_host_in_subnet(self):
        self.assertTrue(homelab_ip_in_network("172.16.1.2", "172.16.1.0/28"))
        self.assertFalse(homelab_ip_in_network("172.16.1.0", "172.16.1.0/28"))
        self.assertFalse(homelab_ip_in_network("172.16.1.16", "172.16.1.0/28"))

    def test_paths_images_and_names_reject_unsafe_values(self):
        self.assertTrue(homelab_safe_absolute_path("/opt/service/data"))
        self.assertFalse(homelab_safe_absolute_path("/"))
        self.assertFalse(homelab_safe_absolute_path("../data"))
        self.assertFalse(homelab_safe_absolute_path("/opt/../etc"))
        self.assertTrue(homelab_safe_name("service_net-1"))
        self.assertFalse(homelab_safe_name("service net"))
        self.assertTrue(homelab_immutable_image("registry.example/app@sha256:" + "a" * 64))
        self.assertFalse(homelab_immutable_image("registry.example/app:latest"))


if __name__ == "__main__":
    unittest.main()
