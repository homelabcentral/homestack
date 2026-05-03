"""Tests for env metadata generator."""

from __future__ import annotations

import json
from pathlib import Path

from server.env import Env


def _write_template(path: Path, *, description: str, required: str) -> None:
    path.write_text(
        "\n".join(
            [
                "# METADATA --- START",
                f"description={description}",
                f"required={required}",
                "# METADATA --- END",
                "",
                "EXAMPLE=1",
            ]
        ),
        encoding="utf-8",
    )


def test_collect_uses_template_filenames(tmp_path: Path):
    env_dir = tmp_path / "00.env"
    env_dir.mkdir(parents=True)

    _write_template(
        env_dir / "host.env.template",
        description="Host vars",
        required="true",
    )
    _write_template(
        env_dir / "email.env.template",
        description="Email vars",
        required="false",
    )

    # Even if raw .env files exist, collect() should represent templates only.
    (env_dir / "host.env").write_text("DUMMY=1\n", encoding="utf-8")
    (env_dir / "email.env").write_text("DUMMY=1\n", encoding="utf-8")

    items = Env(workspace_root=tmp_path).collect()

    assert [item.file_name for item in items] == [
        "email.env.template",
        "host.env.template",
    ]
    assert all(
        name.endswith(".env.template") for name in [item.file_name for item in items]
    )


def test_write_json_emits_template_names_only(tmp_path: Path):
    env_dir = tmp_path / "00.env"
    env_dir.mkdir(parents=True)

    _write_template(
        env_dir / "network.env.template",
        description="Network vars",
        required="yes",
    )
    _write_template(
        env_dir / "vpn.env.template",
        description="VPN vars",
        required="no",
    )

    generator = Env(workspace_root=tmp_path)
    payload = generator.write_json()

    file_names = [item["file_name"] for item in payload]
    assert file_names == ["network.env.template", "vpn.env.template"]
    assert all(name.endswith(".env.template") for name in file_names)

    written = json.loads(
        (tmp_path / "00.api" / "v1" / "env.json").read_text(encoding="utf-8")
    )
    assert written == payload


def test_collect_parses_description_and_required(tmp_path: Path):
    env_dir = tmp_path / "00.env"
    env_dir.mkdir(parents=True)

    _write_template(
        env_dir / "local.env.template",
        description="Local preferences",
        required="1",
    )

    item = Env(workspace_root=tmp_path).collect()[0]

    assert item.file_name == "local.env.template"
    assert item.description == "Local preferences"
    assert item.required is True
