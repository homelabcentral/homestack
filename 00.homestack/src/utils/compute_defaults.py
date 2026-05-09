"""Safe resolver registry for template ``compute=...`` defaults.

This module intentionally supports a tiny allow-list of resolver names and
never executes shell commands or dynamic Python expressions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable

from utils.shared_pref import HostPreferences

_RESOLVER_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MAX_COMPUTED_VALUE_LENGTH = 2048


class ComputeResolverError(ValueError):
    """Raised when ``compute=...`` cannot be safely resolved."""


@dataclass(frozen=True)
class ComputeContext:
    """Trusted context exposed to compute resolvers."""

    host_preferences: HostPreferences | None = None


ResolverFn = Callable[[ComputeContext], str]


def _require_host_prefs(context: ComputeContext, field_name: str) -> HostPreferences:
    prefs = context.host_preferences
    if prefs is None:
        raise ComputeResolverError(
            f"Resolver '{field_name}' requires initialized host preferences"
        )
    return prefs


def _resolve_username(context: ComputeContext) -> str:
    return _require_host_prefs(context, "username").username


def _resolve_uid(context: ComputeContext) -> str:
    uid = _require_host_prefs(context, "uid").uid
    if uid is None:
        raise ComputeResolverError("Resolver 'uid' is unavailable on this platform")
    return str(uid)


def _resolve_gid(context: ComputeContext) -> str:
    gid = _require_host_prefs(context, "gid").gid
    if gid is None:
        raise ComputeResolverError("Resolver 'gid' is unavailable on this platform")
    return str(gid)


def _resolve_docker_gid(context: ComputeContext) -> str:
    docker_gid = _require_host_prefs(context, "docker_gid").docker_gid
    if docker_gid is None:
        raise ComputeResolverError(
            "Resolver 'docker_gid' is unavailable because docker group was not found"
        )
    return str(docker_gid)


_RESOLVERS = MappingProxyType(
    {
        "username": _resolve_username,
        "uid": _resolve_uid,
        "gid": _resolve_gid,
        "docker_gid": _resolve_docker_gid,
    }
)


def allowed_resolvers() -> tuple[str, ...]:
    """Return a stable tuple of all supported resolver names."""
    return tuple(_RESOLVERS.keys())


def resolve_computed_value(resolver_name: str, context: ComputeContext) -> str:
    """Resolve one computed value using a strict allow-list.

    The ``resolver_name`` must be a simple identifier and match one of the
    registered names in this module.
    """
    normalized_name = resolver_name.strip().lower()
    if not normalized_name:
        raise ComputeResolverError("Compute resolver name cannot be empty")

    if not _RESOLVER_NAME_PATTERN.fullmatch(normalized_name):
        raise ComputeResolverError(
            f"Invalid compute resolver '{resolver_name}': only [a-z0-9_] identifiers are allowed"
        )

    resolver = _RESOLVERS.get(normalized_name)
    if resolver is None:
        allowed = ", ".join(allowed_resolvers())
        raise ComputeResolverError(
            f"Unknown compute resolver '{normalized_name}'. Allowed resolvers: {allowed}"
        )

    value = resolver(context)
    if not isinstance(value, str):
        raise ComputeResolverError(
            f"Resolver '{normalized_name}' returned a non-string value"
        )

    resolved = value.strip()
    if not resolved:
        raise ComputeResolverError(f"Resolver '{normalized_name}' returned an empty value")

    if len(resolved) > MAX_COMPUTED_VALUE_LENGTH:
        raise ComputeResolverError(
            f"Resolver '{normalized_name}' returned a value exceeding {MAX_COMPUTED_VALUE_LENGTH} characters"
        )

    return resolved