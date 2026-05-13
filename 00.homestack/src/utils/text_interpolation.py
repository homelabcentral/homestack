"""Text interpolation helpers using project and shared .env values."""

from __future__ import annotations

import re
from pathlib import Path

_ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TOKEN_PATTERN = re.compile(r"\$(\$|\{([A-Za-z_][A-Za-z0-9_]*)(?:(:-|\?)([^}]*))?\})")
_UNRESOLVED_TOKEN_PATTERN = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*(?::-[^}]*)?\}")


class InterpolationError(ValueError):
    """Raised when interpolation cannot be completed safely."""


class MissingVariableError(InterpolationError):
    """Raised when a required variable is missing."""


def _split_key_value(value: str) -> tuple[str, str | None]:
    if "=" not in value:
        return value.strip(), None
    key, raw = value.split("=", 1)

    parsed_value = raw.strip()
    if parsed_value and not parsed_value.startswith(("'", '"')):
        # Preserve hashes inside tokens by only trimming comments
        # that are preceded by whitespace.
        if parsed_value.startswith("#"):
            parsed_value = ""
        else:
            inline_comment_index = parsed_value.find(" #")
            if inline_comment_index != -1:
                parsed_value = parsed_value[:inline_comment_index].rstrip()

    return key.strip(), parsed_value


def _read_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].lstrip()

        key, value = _split_key_value(stripped)
        if not key or not _ENV_KEY_PATTERN.fullmatch(key):
            continue

        parsed = value or ""
        if len(parsed) >= 2 and parsed[0] == parsed[-1] and parsed[0] in {"'", '"'}:
            parsed = parsed[1:-1]

        values[key] = parsed

    return values


def _interpolate_once(text: str, values: dict[str, str], *, strict: bool) -> str:
    def replace(match: re.Match[str]) -> str:
        if match.group(1) == "$":
            return "$"

        name = match.group(2)
        op = match.group(3)
        arg = match.group(4) or ""

        if name in values and values[name] != "":
            return values[name]

        if op == ":-":
            return arg

        if op == "?":
            raise MissingVariableError(arg or f"Missing required variable: {name}")

        if strict:
            raise MissingVariableError(f"Missing variable: {name}")

        return match.group(0)

    return _TOKEN_PATTERN.sub(replace, text)


def _resolve_values(
    values: dict[str, str], *, strict: bool, max_passes: int = 10
) -> dict[str, str]:
    resolved = dict(values)

    for _ in range(max_passes):
        changed = False
        for key, value in list(resolved.items()):
            new_value = _interpolate_once(value, resolved, strict=False)
            if new_value != value:
                resolved[key] = new_value
                changed = True
        if not changed:
            break

    if strict:
        for key, value in resolved.items():
            if _UNRESOLVED_TOKEN_PATTERN.search(value):
                raise InterpolationError(
                    f"Unresolved variable reference in env value for key '{key}': {value}"
                )

    return resolved


def load_interpolation_context(
    shared_env_dir: Path | str,
    project_env_file: Path | str,
    *,
    strict: bool = True,
) -> dict[str, str]:
    """Load interpolation variables from shared and project .env files.

    Shared values are loaded from all ``*.env`` files in ``shared_env_dir``.
    Project values from ``project_env_file`` override shared values.
    """
    shared_dir = Path(shared_env_dir)
    project_env_path = Path(project_env_file)

    merged: dict[str, str] = {}

    if shared_dir.exists():
        for env_file in sorted(shared_dir.glob("*.env")):
            merged.update(_read_env_file(env_file))

    merged.update(_read_env_file(project_env_path))
    return _resolve_values(merged, strict=strict)


def interpolate_text(
    text: str,
    variables: dict[str, str],
    *,
    strict: bool = True,
) -> str:
    """Interpolate placeholders in text using the provided variables."""
    return _interpolate_once(text, variables, strict=strict)


def interpolate_text_with_env(
    text: str,
    *,
    shared_env_dir: Path | str,
    project_env_file: Path | str,
    strict: bool = True,
) -> str:
    """Load env values and interpolate text in one call."""
    values = load_interpolation_context(
        shared_env_dir=shared_env_dir,
        project_env_file=project_env_file,
        strict=strict,
    )
    return interpolate_text(text, values, strict=strict)


def find_unresolved_placeholders(text: str) -> tuple[str, ...]:
    """Return unique unresolved placeholder tokens left in text."""
    found: list[str] = []
    for match in _UNRESOLVED_TOKEN_PATTERN.finditer(text):
        token = match.group(0)
        if token not in found:
            found.append(token)
    return tuple(found)
