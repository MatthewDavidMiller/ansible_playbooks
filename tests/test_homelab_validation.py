import unittest

from filter_plugins.homelab_validation import (
    FilterModule,
    homelab_container_assignable_ip,
    homelab_immutable_image,
    homelab_ip_in_network,
    homelab_safe_absolute_path,
    homelab_safe_name,
    homelab_valid_ipv4_address,
    homelab_valid_ipv4_cidr,
)


class HomelabValidationTests(unittest.TestCase):
    def test_cidr_is_semantic_and_rejects_default_route(self):
        self.assertTrue(homelab_valid_ipv4_cidr("172.16.1.0/28"))
        self.assertFalse(homelab_valid_ipv4_cidr("172.16.1.1/28"))
        self.assertFalse(homelab_valid_ipv4_cidr("0.0.0.0/0"))
        self.assertTrue(homelab_valid_ipv4_cidr("0.0.0.0/0", reject_default=False))
        self.assertFalse(homelab_valid_ipv4_cidr("2001:db8::/64"))
        self.assertFalse(homelab_valid_ipv4_cidr("invalid"))

    def test_ipv4_address_rejects_ipv6_and_invalid_values(self):
        self.assertTrue(homelab_valid_ipv4_address("192.0.2.10"))
        self.assertFalse(homelab_valid_ipv4_address("2001:db8::1"))
        self.assertFalse(homelab_valid_ipv4_address("invalid"))

    def test_static_ip_must_be_usable_host_in_subnet(self):
        self.assertTrue(homelab_ip_in_network("172.16.1.2", "172.16.1.0/28"))
        self.assertFalse(homelab_ip_in_network("172.16.1.0", "172.16.1.0/28"))
        self.assertFalse(homelab_ip_in_network("172.16.1.15", "172.16.1.0/28"))
        self.assertFalse(homelab_ip_in_network("172.16.1.16", "172.16.1.0/28"))
        self.assertFalse(homelab_ip_in_network("invalid", "172.16.1.0/28"))
        self.assertFalse(homelab_ip_in_network("172.16.1.2", "invalid"))

    def test_assignable_ip_rejects_the_podman_gateway(self):
        # Podman claims the first host address of a network as the gateway, so
        # a container that requests it never starts.
        self.assertFalse(homelab_container_assignable_ip("172.16.1.41", "172.16.1.40/29"))
        self.assertTrue(homelab_container_assignable_ip("172.16.1.42", "172.16.1.40/29"))
        self.assertTrue(homelab_container_assignable_ip("172.16.1.46", "172.16.1.40/29"))
        self.assertFalse(homelab_container_assignable_ip("172.16.1.47", "172.16.1.40/29"))
        self.assertFalse(homelab_container_assignable_ip("172.16.1.50", "172.16.1.40/29"))
        self.assertFalse(homelab_container_assignable_ip("172.16.1.1", "172.16.1.0/28"))
        self.assertTrue(homelab_container_assignable_ip("172.16.1.2", "172.16.1.0/28"))
        self.assertFalse(homelab_container_assignable_ip("invalid", "172.16.1.0/28"))
        self.assertFalse(homelab_container_assignable_ip("172.16.1.2", "invalid"))
        self.assertFalse(homelab_container_assignable_ip("172.16.1.2", "172.16.1.2/32"))

    def test_paths_images_and_names_reject_unsafe_values(self):
        self.assertTrue(homelab_safe_absolute_path("/opt/service/data"))
        self.assertFalse(homelab_safe_absolute_path("/"))
        self.assertFalse(homelab_safe_absolute_path("../data"))
        self.assertFalse(homelab_safe_absolute_path("/opt/../etc"))
        self.assertFalse(homelab_safe_absolute_path(" /opt/service"))
        self.assertFalse(homelab_safe_absolute_path("/opt/service\x00data"))
        self.assertTrue(homelab_safe_name("service_net-1"))
        self.assertFalse(homelab_safe_name("service net"))
        self.assertFalse(homelab_safe_name("."))
        self.assertFalse(homelab_safe_name(".."))
        self.assertTrue(homelab_immutable_image("registry.example/app@sha256:" + "a" * 64))
        self.assertFalse(homelab_immutable_image("registry.example/app:latest"))
        self.assertFalse(homelab_immutable_image("registry.example/app@sha256:" + "A" * 64))

    def test_filter_module_exports_compatibility_aliases(self):
        filters = FilterModule().filters()
        self.assertIs(filters["homelab_ip_in_subnet"], homelab_ip_in_network)
        self.assertIs(
            filters["homelab_container_assignable_ip"], homelab_container_assignable_ip
        )
        self.assertIs(filters["homelab_immutable_digest_ref"], homelab_immutable_image)


if __name__ == "__main__":
    unittest.main()
