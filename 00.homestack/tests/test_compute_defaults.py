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
) -> HostPreferences:
    return HostPreferences(
        username=username,
        uid=uid,
        gid=gid,
        docker_gid=docker_gid,
        architecture="x86_64",
        cpu_count=8,
        ram_mb=32768,
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
        "tailscale_ip",
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
    with pytest.raises(ComputeResolverError, match="requires initialized host preferences"):
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
