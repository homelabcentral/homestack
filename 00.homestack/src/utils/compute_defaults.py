"""Safe resolver registry for template ``compute=...`` defaults.

This module intentionally supports a tiny allow-list of resolver names and
never executes shell commands or dynamic Python expressions.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import struct
from dataclasses import dataclass
from fcntl import ioctl
from types import MappingProxyType
from typing import Callable

import httpx

from utils.shared_pref import HostPreferences

_RESOLVER_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MAX_COMPUTED_VALUE_LENGTH = 2048
_SIOCGIFADDR = 0x8915
_IGNORED_INTERFACE_PREFIXES = (
    "lo",
    "docker",
    "br-",
    "veth",
    "virbr",
    "vmnet",
    "zt",
    "tun",
    "tap",
    "wg",
)
_ETHERNET_INTERFACE_PREFIXES = ("eth", "en")
_WIFI_INTERFACE_PREFIXES = ("wl", "wlan", "wifi")
_TAILSCALE_INTERFACE_PREFIXES = ("tailscale",)
_PUBLIC_IP_SERVICES = (
    "https://api.ipify.org",
    "https://checkip.amazonaws.com",
    "https://ifconfig.me/ip",
)
_PUBLIC_IP_TIMEOUT_SECONDS = 3.0


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


def _list_interface_ipv4_addresses() -> list[tuple[str, str]]:
    """Return interface names with IPv4 addresses discovered from the host."""
    interfaces = [name for _, name in socket.if_nameindex()]
    addresses: list[tuple[str, str]] = []

    for interface_name in interfaces:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                request = struct.pack("256s", interface_name[:15].encode("utf-8"))
                response = ioctl(sock.fileno(), _SIOCGIFADDR, request)
                ip_text = socket.inet_ntoa(response[20:24])
                addresses.append((interface_name, ip_text))
        except OSError:
            # Interface has no IPv4 address (or cannot be inspected).
            continue

    return addresses


def _is_private_lan_ipv4(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False

    return (
        isinstance(ip, ipaddress.IPv4Address)
        and ip.is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_multicast
        and not ip.is_unspecified
    )


def _is_public_ip(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False

    return ip.is_global and not ip.is_multicast and not ip.is_unspecified


def _is_tailscale_interface(interface_name: str) -> bool:
    normalized = interface_name.strip().lower()
    return normalized.startswith(_TAILSCALE_INTERFACE_PREFIXES)


def _is_ignored_for_private_ip(interface_name: str) -> bool:
    normalized = interface_name.strip().lower()
    if normalized.startswith(_IGNORED_INTERFACE_PREFIXES):
        return True
    return _is_tailscale_interface(normalized)


def _private_interface_priority(interface_name: str) -> int:
    normalized = interface_name.strip().lower()
    if normalized.startswith(_ETHERNET_INTERFACE_PREFIXES):
        return 0
    if normalized.startswith(_WIFI_INTERFACE_PREFIXES):
        return 1
    return 2


def _resolve_private_ip(_context: ComputeContext) -> str:
    candidates: list[tuple[str, str]] = []
    for interface_name, ip_text in _list_interface_ipv4_addresses():
        if _is_ignored_for_private_ip(interface_name):
            continue
        if not _is_private_lan_ipv4(ip_text):
            continue
        candidates.append((interface_name, ip_text))

    if not candidates:
        raise ComputeResolverError(
            "Resolver 'private_ip' could not find a private LAN IPv4 address"
        )

    candidates.sort(key=lambda item: (_private_interface_priority(item[0]), item[0]))
    return candidates[0][1]


def _resolve_tailscale_ip(_context: ComputeContext) -> str:
    for interface_name, ip_text in _list_interface_ipv4_addresses():
        if not _is_tailscale_interface(interface_name):
            continue
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            continue
        if isinstance(ip, ipaddress.IPv4Address):
            return ip_text

    raise ComputeResolverError(
        "Resolver 'tailscale_ip' could not find an IPv4 address on a tailscale interface"
    )


def _fetch_public_ip_from_services() -> str:
    """Resolve the host public IP via a tiny HTTPS allow-list.

    This intentionally uses Python networking only and never shells out.
    """
    timeout = httpx.Timeout(_PUBLIC_IP_TIMEOUT_SECONDS)

    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for service_url in _PUBLIC_IP_SERVICES:
            try:
                response = client.get(service_url, headers={"Accept": "text/plain"})
                response.raise_for_status()
            except httpx.HTTPError:
                continue

            candidate = response.text.strip()
            if _is_public_ip(candidate):
                return candidate

    raise ComputeResolverError(
        "Resolver 'public_ip' could not determine a public IP from trusted HTTPS services"
    )


def _resolve_public_ip(_context: ComputeContext) -> str:
    return _fetch_public_ip_from_services()


_ZONEINFO_PREFIX = "/usr/share/zoneinfo/"


def _fetch_system_timezone() -> str:
    """Return the machine's IANA timezone name using filesystem sources only.

    Primary: ``/etc/localtime`` symlink target stripped of its zoneinfo prefix.
    Fallback: ``/etc/timezone`` plain-text file.
    """
    try:
        target = os.readlink("/etc/localtime")
        # Normalise path separators and strip the zoneinfo prefix.
        target = target.replace("\\", "/")
        idx = target.find(_ZONEINFO_PREFIX)
        if idx != -1:
            iana_name = target[idx + len(_ZONEINFO_PREFIX) :]
            if iana_name:
                return iana_name
    except OSError:
        pass

    try:
        with open("/etc/timezone", encoding="utf-8") as fh:
            iana_name = fh.read().strip()
        if iana_name:
            return iana_name
    except OSError:
        pass

    raise ComputeResolverError(
        "Resolver 'timezone' could not determine system timezone"
    )


def _resolve_timezone(_context: ComputeContext) -> str:
    return _fetch_system_timezone()


_RESOLVERS = MappingProxyType(
    {
        "username": _resolve_username,
        "uid": _resolve_uid,
        "gid": _resolve_gid,
        "docker_gid": _resolve_docker_gid,
        "private_ip": _resolve_private_ip,
        "public_ip": _resolve_public_ip,
        "tailscale_ip": _resolve_tailscale_ip,
        "timezone": _resolve_timezone,
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
        raise ComputeResolverError(
            f"Resolver '{normalized_name}' returned an empty value"
        )

    if len(resolved) > MAX_COMPUTED_VALUE_LENGTH:
        raise ComputeResolverError(
            f"Resolver '{normalized_name}' returned a value exceeding {MAX_COMPUTED_VALUE_LENGTH} characters"
        )

    return resolved
