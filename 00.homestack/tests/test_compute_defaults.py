"""Tests for safe compute default resolver registry."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest
from utils.compute_defaults import (
    ComputeContext,
    ComputeResolverError,
    allowed_resolvers,
    resolve_computed_value,
)
from utils.shared_pref import HostPreferences


def _host_prefs(
    *,
    username: str = "alice",
    uid: int | None = 1000,
    gid: int | None = 1000,
    docker_gid: int | None = 998,
    cpu_count: int = 8,
    ram_mb: int | None = 32768,
) -> HostPreferences:
    return HostPreferences(
        username=username,
        uid=uid,
        gid=gid,
        docker_gid=docker_gid,
        architecture="x86_64",
        cpu_count=cpu_count,
        ram_mb=ram_mb,
        install_dir="/tmp/homestack",
        install_dir_total_gb=128.0,
    )


def test_allowed_resolvers_is_expected_allow_list():
    assert allowed_resolvers() == (
        "username",
        "uid",
        "gid",
        "docker_gid",
        "private_ip",
        "public_ip",
        "tailscale_ip",
        "timezone",
        "host_ram",
        "host_cpu",
    )


@pytest.mark.parametrize(
    ("resolver_name", "expected"),
    [
        ("username", "alice"),
        ("uid", "1000"),
        ("gid", "1000"),
        ("docker_gid", "998"),
    ],
)
def test_resolve_computed_value_known_resolvers(resolver_name: str, expected: str):
    context = ComputeContext(host_preferences=_host_prefs())
    assert resolve_computed_value(resolver_name, context) == expected


@pytest.mark.parametrize(
    "resolver_name",
    [
        "id -u",
        "$(id -u)",
        "uid;rm -rf /",
        "__import__",
        "uid()",
        "uid docker",
    ],
)
def test_resolve_computed_value_rejects_command_like_names(resolver_name: str):
    context = ComputeContext(host_preferences=_host_prefs())
    with pytest.raises(ComputeResolverError):
        resolve_computed_value(resolver_name, context)


def test_resolve_computed_value_rejects_unknown_name():
    context = ComputeContext(host_preferences=_host_prefs())
    with pytest.raises(ComputeResolverError, match="Unknown compute resolver"):
        resolve_computed_value("hostname", context)


def test_resolve_computed_value_requires_host_preferences():
    context = ComputeContext(host_preferences=None)
    with pytest.raises(
        ComputeResolverError, match="requires initialized host preferences"
    ):
        resolve_computed_value("uid", context)


def test_resolve_computed_value_rejects_missing_docker_gid():
    context = ComputeContext(host_preferences=_host_prefs(docker_gid=None))
    with pytest.raises(ComputeResolverError, match="docker group"):
        resolve_computed_value("docker_gid", context)


def test_private_ip_prefers_ethernet_over_wifi_interfaces():
    context = ComputeContext(host_preferences=_host_prefs())

    with patch(
        "utils.compute_defaults._list_interface_ipv4_addresses",
        return_value=[
            ("wlan0", "192.168.1.20"),
            ("eth0", "10.10.10.5"),
            ("tailscale0", "100.88.1.2"),
        ],
    ):
        resolved = resolve_computed_value("private_ip", context)

    assert resolved == "10.10.10.5"


def test_private_ip_uses_wifi_when_no_ethernet_is_available():
    context = ComputeContext(host_preferences=_host_prefs())

    with patch(
        "utils.compute_defaults._list_interface_ipv4_addresses",
        return_value=[
            ("wlan0", "192.168.1.20"),
            ("tailscale0", "100.88.1.2"),
        ],
    ):
        resolved = resolve_computed_value("private_ip", context)

    assert resolved == "192.168.1.20"


def test_private_ip_ignores_non_private_or_virtual_interfaces():
    context = ComputeContext(host_preferences=_host_prefs())

    with patch(
        "utils.compute_defaults._list_interface_ipv4_addresses",
        return_value=[
            ("lo", "127.0.0.1"),
            ("docker0", "172.17.0.1"),
            ("tailscale0", "100.88.1.2"),
            ("eth0", "8.8.8.8"),
        ],
    ):
        with pytest.raises(ComputeResolverError, match="private LAN IPv4"):
            resolve_computed_value("private_ip", context)


def test_tailscale_ip_reads_tailscale_interface():
    context = ComputeContext(host_preferences=_host_prefs())

    with patch(
        "utils.compute_defaults._list_interface_ipv4_addresses",
        return_value=[
            ("eth0", "10.10.10.5"),
            ("tailscale0", "100.88.1.2"),
        ],
    ):
        resolved = resolve_computed_value("tailscale_ip", context)

    assert resolved == "100.88.1.2"


def test_tailscale_ip_requires_tailscale_interface():
    context = ComputeContext(host_preferences=_host_prefs())

    with patch(
        "utils.compute_defaults._list_interface_ipv4_addresses",
        return_value=[("eth0", "10.10.10.5")],
    ):
        with pytest.raises(ComputeResolverError, match="tailscale interface"):
            resolve_computed_value("tailscale_ip", context)


def test_public_ip_uses_trusted_https_service_result():
    context = ComputeContext(host_preferences=_host_prefs())

    with patch(
        "utils.compute_defaults._fetch_public_ip_from_services",
        return_value="203.0.113.10",
    ):
        resolved = resolve_computed_value("public_ip", context)

    assert resolved == "203.0.113.10"


def test_public_ip_fails_when_service_resolution_fails():
    context = ComputeContext(host_preferences=_host_prefs())

    with patch(
        "utils.compute_defaults._fetch_public_ip_from_services",
        side_effect=ComputeResolverError(
            "Resolver 'public_ip' could not determine a public IP from trusted HTTPS services"
        ),
    ):
        with pytest.raises(ComputeResolverError, match="trusted HTTPS services"):
            resolve_computed_value("public_ip", context)


def test_private_ip_does_not_use_subprocess_commands():
    context = ComputeContext(host_preferences=_host_prefs())

    with (
        patch("subprocess.run") as mock_subprocess_run,
        patch("subprocess.Popen") as mock_subprocess_popen,
        patch(
            "utils.compute_defaults._list_interface_ipv4_addresses",
            return_value=[("eth0", "10.10.10.5")],
        ),
    ):
        resolved = resolve_computed_value("private_ip", context)

    assert resolved == "10.10.10.5"
    mock_subprocess_run.assert_not_called()
    mock_subprocess_popen.assert_not_called()


def test_tailscale_ip_does_not_use_subprocess_commands():
    context = ComputeContext(host_preferences=_host_prefs())

    with (
        patch("subprocess.run") as mock_subprocess_run,
        patch("subprocess.Popen") as mock_subprocess_popen,
        patch(
            "utils.compute_defaults._list_interface_ipv4_addresses",
            return_value=[("tailscale0", "100.88.1.2")],
        ),
    ):
        resolved = resolve_computed_value("tailscale_ip", context)

    assert resolved == "100.88.1.2"
    mock_subprocess_run.assert_not_called()
    mock_subprocess_popen.assert_not_called()


def test_public_ip_does_not_use_subprocess_commands():
    context = ComputeContext(host_preferences=_host_prefs())

    with (
        patch("subprocess.run") as mock_subprocess_run,
        patch("subprocess.Popen") as mock_subprocess_popen,
        patch(
            "utils.compute_defaults._fetch_public_ip_from_services",
            return_value="203.0.113.10",
        ),
    ):
        resolved = resolve_computed_value("public_ip", context)

    assert resolved == "203.0.113.10"
    mock_subprocess_run.assert_not_called()
    mock_subprocess_popen.assert_not_called()


def test_malicious_compute_does_not_invoke_shell_or_eval_paths():
    context = ComputeContext(host_preferences=_host_prefs())

    with (
        patch("os.system") as mock_os_system,
        patch.object(subprocess, "run") as mock_subprocess_run,
        patch.object(subprocess, "Popen") as mock_subprocess_popen,
        patch("builtins.eval") as mock_eval,
    ):
        with pytest.raises(ComputeResolverError):
            resolve_computed_value("__import__('os').system('id')", context)

    mock_os_system.assert_not_called()
    mock_subprocess_run.assert_not_called()
    mock_subprocess_popen.assert_not_called()
    mock_eval.assert_not_called()


def test_timezone_reads_localtime_symlink():
    context = ComputeContext(host_preferences=_host_prefs())

    with patch(
        "utils.compute_defaults.os.readlink",
        return_value="/usr/share/zoneinfo/America/New_York",
    ):
        resolved = resolve_computed_value("timezone", context)

    assert resolved == "America/New_York"


def test_timezone_falls_back_to_etc_timezone():
    context = ComputeContext(host_preferences=_host_prefs())

    with (
        patch("utils.compute_defaults.os.readlink", side_effect=OSError),
        patch(
            "builtins.open", return_value=__import__("io").StringIO("Europe/Berlin\n")
        ),
    ):
        resolved = resolve_computed_value("timezone", context)

    assert resolved == "Europe/Berlin"


def test_timezone_fails_when_neither_source_available():
    context = ComputeContext(host_preferences=_host_prefs())

    with (
        patch("utils.compute_defaults.os.readlink", side_effect=OSError),
        patch("builtins.open", side_effect=OSError),
    ):
        with pytest.raises(
            ComputeResolverError, match="could not determine system timezone"
        ):
            resolve_computed_value("timezone", context)


def test_timezone_does_not_use_subprocess_commands():
    context = ComputeContext(host_preferences=_host_prefs())

    with (
        patch("subprocess.run") as mock_subprocess_run,
        patch("subprocess.Popen") as mock_subprocess_popen,
        patch(
            "utils.compute_defaults.os.readlink",
            return_value="/usr/share/zoneinfo/Europe/London",
        ),
    ):
        resolved = resolve_computed_value("timezone", context)

    assert resolved == "Europe/London"
    mock_subprocess_run.assert_not_called()
    mock_subprocess_popen.assert_not_called()


class TestHostRamResolvers:
    """Tests for host_ram and host_ram_<percent> resolvers."""

    def test_host_ram_total_formats_gigabytes(self):
        """Test that total RAM is formatted as largest whole unit."""
        context = ComputeContext(host_preferences=_host_prefs(ram_mb=32768))
        resolved = resolve_computed_value("host_ram", context)
        assert resolved == "32G"

    def test_host_ram_total_formats_megabytes(self):
        """Test that smaller RAM values are formatted as MB."""
        context = ComputeContext(host_preferences=_host_prefs(ram_mb=512))
        resolved = resolve_computed_value("host_ram", context)
        assert resolved == "512M"

    def test_host_ram_total_formats_awkward_values(self):
        """Test that odd values use the largest whole unit."""
        context = ComputeContext(host_preferences=_host_prefs(ram_mb=16000))
        resolved = resolve_computed_value("host_ram", context)
        # 16000 / 1024 = 15.625, rounds to 16
        assert resolved == "16G"

    def test_host_ram_total_unavailable_on_platform(self):
        """Test that missing RAM data raises appropriate error."""
        prefs = _host_prefs(ram_mb=None)
        context = ComputeContext(host_preferences=prefs)
        with pytest.raises(ComputeResolverError, match="could not determine host RAM"):
            resolve_computed_value("host_ram", context)

    def test_host_ram_50pct_of_32g(self):
        """Test 50% RAM calculation."""
        context = ComputeContext(host_preferences=_host_prefs(ram_mb=32768))
        resolved = resolve_computed_value("host_ram_50", context)
        assert resolved == "16G"

    def test_host_ram_25pct_of_16g(self):
        """Test 25% RAM calculation."""
        context = ComputeContext(host_preferences=_host_prefs(ram_mb=16000))
        resolved = resolve_computed_value("host_ram_25", context)
        # 25% of 16000 = 4000 MB; 4000 / 1024 = 3.906, rounds to 4
        assert resolved == "4G"

    def test_host_ram_80pct_percentage(self):
        """Test 80% RAM calculation."""
        context = ComputeContext(host_preferences=_host_prefs(ram_mb=16000))
        resolved = resolve_computed_value("host_ram_80", context)
        # 80% of 16000 = 12800 MB; 12800 / 1024 = 12.5, rounds to 12 (banker's rounding) or 13 (round-half-up)
        assert resolved in ("12G", "13G")

    def test_host_ram_0pct_minimum(self):
        """Test 0% boundary condition."""
        context = ComputeContext(host_preferences=_host_prefs(ram_mb=32768))
        resolved = resolve_computed_value("host_ram_0", context)
        assert resolved == "0M"

    def test_host_ram_100pct_maximum(self):
        """Test 100% boundary condition."""
        context = ComputeContext(host_preferences=_host_prefs(ram_mb=32768))
        resolved = resolve_computed_value("host_ram_100", context)
        assert resolved == "32G"

    def test_host_ram_percent_rejects_over_100(self):
        """Test that percentages > 100 are rejected."""
        context = ComputeContext(host_preferences=_host_prefs())
        with pytest.raises(ComputeResolverError, match="invalid percent"):
            resolve_computed_value("host_ram_150", context)

    def test_host_ram_percent_rejects_multiple_over_100_values(self):
        """Test that various over-100 percentages are all rejected."""
        context = ComputeContext(host_preferences=_host_prefs())
        for over_100_value in [101, 110, 200, 999]:
            with pytest.raises(ComputeResolverError, match="invalid percent"):
                resolve_computed_value(f"host_ram_{over_100_value}", context)

    def test_host_ram_percent_rejects_non_numeric(self):
        """Test that non-numeric suffixes are rejected."""
        context = ComputeContext(host_preferences=_host_prefs())
        with pytest.raises(ComputeResolverError, match="non-numeric suffix"):
            resolve_computed_value("host_ram_abc", context)

    def test_host_ram_percent_validation_with_invalid_name_pattern(self):
        """Test that identifier pattern validation rejects invalid characters."""
        context = ComputeContext(host_preferences=_host_prefs())
        # These should fail at the identifier pattern validation stage
        with pytest.raises(
            ComputeResolverError, match="only \\[a-z0-9_\\] identifiers"
        ):
            resolve_computed_value("host_ram_@50", context)

    def test_host_ram_boundary_values(self):
        """Test boundary cases at 0 and 100 percent."""
        context = ComputeContext(host_preferences=_host_prefs(ram_mb=32768))
        # 0% should resolve successfully
        resolved_0 = resolve_computed_value("host_ram_0", context)
        assert resolved_0 == "0M"
        # 100% should resolve successfully
        resolved_100 = resolve_computed_value("host_ram_100", context)
        assert resolved_100 == "32G"


class TestHostCpuResolvers:
    """Tests for host_cpu and host_cpu_<percent> resolvers."""

    def test_host_cpu_total_returns_thread_count(self):
        """Test that total CPU returns thread count as string."""
        context = ComputeContext(host_preferences=_host_prefs(cpu_count=8))
        resolved = resolve_computed_value("host_cpu", context)
        assert resolved == "8"

    def test_host_cpu_total_various_counts(self):
        """Test CPU resolution for different thread counts."""
        for count in [1, 4, 16, 32]:
            context = ComputeContext(host_preferences=_host_prefs(cpu_count=count))
            resolved = resolve_computed_value("host_cpu", context)
            assert resolved == str(count)

    def test_host_cpu_50pct_of_8_threads(self):
        """Test 50% CPU calculation."""
        context = ComputeContext(host_preferences=_host_prefs(cpu_count=8))
        resolved = resolve_computed_value("host_cpu_50", context)
        assert resolved == "4.00"

    def test_host_cpu_25pct_of_8_threads(self):
        """Test 25% CPU calculation."""
        context = ComputeContext(host_preferences=_host_prefs(cpu_count=8))
        resolved = resolve_computed_value("host_cpu_25", context)
        assert resolved == "2.00"

    def test_host_cpu_80pct_of_8_threads(self):
        """Test 80% CPU calculation."""
        context = ComputeContext(host_preferences=_host_prefs(cpu_count=8))
        resolved = resolve_computed_value("host_cpu_80", context)
        assert resolved == "6.40"

    def test_host_cpu_percent_rounds_to_2_decimals(self):
        """Test that CPU percentages are rounded to 2 decimal places."""
        context = ComputeContext(host_preferences=_host_prefs(cpu_count=7))
        resolved = resolve_computed_value("host_cpu_33", context)
        # 33% of 7 = 2.31
        assert resolved == "2.31"

    def test_host_cpu_0pct_minimum(self):
        """Test 0% boundary condition."""
        context = ComputeContext(host_preferences=_host_prefs(cpu_count=8))
        resolved = resolve_computed_value("host_cpu_0", context)
        assert resolved == "0.00"

    def test_host_cpu_100pct_maximum(self):
        """Test 100% boundary condition."""
        context = ComputeContext(host_preferences=_host_prefs(cpu_count=8))
        resolved = resolve_computed_value("host_cpu_100", context)
        assert resolved == "8.00"

    def test_host_cpu_percent_rejects_over_100(self):
        """Test that percentages > 100 are rejected."""
        context = ComputeContext(host_preferences=_host_prefs())
        with pytest.raises(ComputeResolverError, match="invalid percent"):
            resolve_computed_value("host_cpu_150", context)

    def test_host_cpu_percent_rejects_multiple_over_100_values(self):
        """Test that various over-100 percentages are all rejected."""
        context = ComputeContext(host_preferences=_host_prefs())
        for over_100_value in [101, 110, 200, 999]:
            with pytest.raises(ComputeResolverError, match="invalid percent"):
                resolve_computed_value(f"host_cpu_{over_100_value}", context)

    def test_host_cpu_percent_rejects_non_numeric(self):
        """Test that non-numeric suffixes are rejected."""
        context = ComputeContext(host_preferences=_host_prefs())
        with pytest.raises(ComputeResolverError, match="non-numeric suffix"):
            resolve_computed_value("host_cpu_abc", context)

    def test_host_cpu_percent_validation_with_invalid_name_pattern(self):
        """Test that identifier pattern validation rejects invalid characters."""
        context = ComputeContext(host_preferences=_host_prefs())
        # These should fail at the identifier pattern validation stage
        with pytest.raises(
            ComputeResolverError, match="only \\[a-z0-9_\\] identifiers"
        ):
            resolve_computed_value("host_cpu_@50", context)

    def test_host_cpu_boundary_values(self):
        """Test boundary cases at 0 and 100 percent."""
        context = ComputeContext(host_preferences=_host_prefs(cpu_count=8))
        # 0% should resolve successfully
        resolved_0 = resolve_computed_value("host_cpu_0", context)
        assert resolved_0 == "0.00"
        # 100% should resolve successfully
        resolved_100 = resolve_computed_value("host_cpu_100", context)
        assert resolved_100 == "8.00"
