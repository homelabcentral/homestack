from __future__ import annotations

from pathlib import Path

import pytest
from utils.text_interpolation import (
    InterpolationError,
    MissingVariableError,
    find_unresolved_placeholders,
    interpolate_text,
    interpolate_text_with_env,
    load_interpolation_context,
)


def test_interpolate_text_with_shared_and_project_env(tmp_path: Path) -> None:
    shared = tmp_path / "00.env"
    shared.mkdir()
    (shared / "host.env").write_text(
        "SUBDOMAIN=lab\nDOMAIN=example\n", encoding="utf-8"
    )
    (shared / "network.env").write_text("IP_PRIVATE=10.0.0.10\n", encoding="utf-8")

    project_env = tmp_path / ".env"
    project_env.write_text("APP_NAME=immich\n", encoding="utf-8")

    text = "https://${APP_NAME}.${SUBDOMAIN}.${DOMAIN}.com"
    result = interpolate_text_with_env(
        text,
        shared_env_dir=shared,
        project_env_file=project_env,
    )

    assert result == "https://immich.lab.example.com"


def test_project_env_overrides_shared_env(tmp_path: Path) -> None:
    shared = tmp_path / "00.env"
    shared.mkdir()
    (shared / "host.env").write_text("DOMAIN=shared.example\n", encoding="utf-8")

    project_env = tmp_path / ".env"
    project_env.write_text("DOMAIN=project.example\n", encoding="utf-8")

    result = interpolate_text_with_env(
        "https://${DOMAIN}",
        shared_env_dir=shared,
        project_env_file=project_env,
    )
    assert result == "https://project.example"


def test_supports_default_and_required_syntax(tmp_path: Path) -> None:
    shared = tmp_path / "00.env"
    shared.mkdir()
    project_env = tmp_path / ".env"
    project_env.write_text("", encoding="utf-8")

    value = interpolate_text_with_env(
        "http://${HOST:-localhost}:${PORT:-8080}",
        shared_env_dir=shared,
        project_env_file=project_env,
    )
    assert value == "http://localhost:8080"

    with pytest.raises(MissingVariableError, match="Missing required variable"):
        interpolate_text_with_env(
            "${TOKEN?Missing required variable TOKEN}",
            shared_env_dir=shared,
            project_env_file=project_env,
        )


def test_escaped_dollar_is_preserved(tmp_path: Path) -> None:
    shared = tmp_path / "00.env"
    shared.mkdir()
    project_env = tmp_path / ".env"
    project_env.write_text("PRICE=42\n", encoding="utf-8")

    value = interpolate_text_with_env(
        "Cost: $$${PRICE}",
        shared_env_dir=shared,
        project_env_file=project_env,
    )
    assert value == "Cost: $42"


def test_resolves_dependencies_inside_env_values(tmp_path: Path) -> None:
    shared = tmp_path / "00.env"
    shared.mkdir()
    (shared / "host.env").write_text(
        "SUBDOMAIN=home\n"
        "DOMAIN=example.com\n"
        "APP_URL=https://${APP_NAME}.${SUBDOMAIN}.${DOMAIN}\n",
        encoding="utf-8",
    )

    project_env = tmp_path / ".env"
    project_env.write_text("APP_NAME=vaultwarden\n", encoding="utf-8")

    ctx = load_interpolation_context(shared, project_env)
    assert ctx["APP_URL"] == "https://vaultwarden.home.example.com"

    out = interpolate_text("URL: ${APP_URL}", ctx)
    assert out == "URL: https://vaultwarden.home.example.com"


def test_unresolved_reference_raises_in_strict_mode(tmp_path: Path) -> None:
    shared = tmp_path / "00.env"
    shared.mkdir()
    (shared / "host.env").write_text("APP_URL=https://${MISSING}\n", encoding="utf-8")
    project_env = tmp_path / ".env"
    project_env.write_text("", encoding="utf-8")

    with pytest.raises(InterpolationError, match="Unresolved variable reference"):
        load_interpolation_context(shared, project_env, strict=True)


def test_find_unresolved_placeholders_returns_unique_tokens() -> None:
    text = "A ${ONE} and ${TWO} and again ${ONE}"
    assert find_unresolved_placeholders(text) == ("${ONE}", "${TWO}")
