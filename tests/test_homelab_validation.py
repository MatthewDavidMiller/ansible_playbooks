import json
import unittest

from filter_plugins.homelab_validation import (
    FilterModule,
    homelab_container_assignable_ip,
    homelab_immutable_image,
    homelab_ip_in_network,
    homelab_network_needs_replacement,
    homelab_safe_absolute_path,
    homelab_safe_name,
    homelab_valid_ipv4_address,
    homelab_valid_ipv4_cidr,
)


def inspect_output(*, internal=True, subnets=("172.16.1.0/28",), internal_key="internal"):
    network = {"name": "example_net"}
    if internal_key is not None:
        network[internal_key] = internal
    if subnets is not None:
        network["subnets"] = [{"subnet": subnet} for subnet in subnets]
    return json.dumps([network])


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
        self.assertFalse(homelab_safe_name("-option"))
        self.assertFalse(homelab_safe_name("."))
        self.assertFalse(homelab_safe_name(".."))
        self.assertTrue(homelab_immutable_image("registry.example/app@sha256:" + "a" * 64))
        self.assertFalse(homelab_immutable_image("registry.example/app:latest"))
        self.assertFalse(homelab_immutable_image("registry.example/app@sha256:" + "A" * 64))

    def test_matching_network_is_left_alone(self):
        self.assertFalse(
            homelab_network_needs_replacement(inspect_output(), "172.16.1.0/28")
        )

    def test_non_internal_network_is_replaced(self):
        self.assertTrue(
            homelab_network_needs_replacement(
                inspect_output(internal=False), "172.16.1.0/28"
            )
        )

    def test_legacy_capitalized_internal_key_is_honored(self):
        # Podman 4 reports `internal`; older releases reported `Internal`.
        self.assertFalse(
            homelab_network_needs_replacement(
                inspect_output(internal_key="Internal"), "172.16.1.0/28"
            )
        )
        self.assertTrue(
            homelab_network_needs_replacement(
                inspect_output(internal=False, internal_key="Internal"), "172.16.1.0/28"
            )
        )

    def test_missing_internal_flag_counts_as_non_internal(self):
        self.assertTrue(
            homelab_network_needs_replacement(
                inspect_output(internal_key=None), "172.16.1.0/28"
            )
        )

    def test_subnet_drift_is_replaced(self):
        self.assertTrue(
            homelab_network_needs_replacement(
                inspect_output(subnets=("172.16.9.0/28",)), "172.16.1.0/28"
            )
        )
        self.assertFalse(
            homelab_network_needs_replacement(
                inspect_output(subnets=("172.16.9.0/28", "172.16.1.0/28")),
                "172.16.1.0/28",
            )
        )

    def test_network_without_declared_subnet_only_enforces_internal(self):
        """Route networks with no deterministic subnet accept whatever Podman assigned."""
        self.assertFalse(
            homelab_network_needs_replacement(inspect_output(subnets=("10.89.0.0/24",)), "")
        )
        self.assertTrue(
            homelab_network_needs_replacement(
                inspect_output(internal=False, subnets=("10.89.0.0/24",)), ""
            )
        )

    def test_missing_subnet_data_is_replaced_when_a_subnet_is_declared(self):
        self.assertTrue(
            homelab_network_needs_replacement(
                inspect_output(subnets=None), "172.16.1.0/28"
            )
        )

    def test_external_network_mode_is_reconciled_exactly(self):
        self.assertFalse(
            homelab_network_needs_replacement(
                inspect_output(internal=False), "172.16.1.0/28", False
            )
        )
        self.assertTrue(
            homelab_network_needs_replacement(
                inspect_output(internal=True), "172.16.1.0/28", False
            )
        )

    def test_invalid_internal_flag_fails_loudly(self):
        output = json.dumps(
            [{"name": "example_net", "internal": "false", "subnets": []}]
        )
        with self.assertRaisesRegex(ValueError, "invalid internal flag"):
            homelab_network_needs_replacement(output)

    def test_unreadable_inspect_output_fails_loudly(self):
        for output in ("", "not-json", "{}", "[]", "[null]"):
            with self.subTest(output=output):
                with self.assertRaises(ValueError):
                    homelab_network_needs_replacement(output, "172.16.1.0/28")

    def test_filter_module_exports_compatibility_aliases(self):
        filters = FilterModule().filters()
        self.assertIs(filters["homelab_ip_in_subnet"], homelab_ip_in_network)
        self.assertIs(
            filters["homelab_container_assignable_ip"], homelab_container_assignable_ip
        )
        self.assertIs(filters["homelab_immutable_digest_ref"], homelab_immutable_image)


if __name__ == "__main__":
    unittest.main()
