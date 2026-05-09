"""Tests for safe compute default resolver registry."""

from __future__ import annotations

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
    assert allowed_resolvers() == ("username", "uid", "gid", "docker_gid")


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
