"""Tests for server.main orchestration entrypoint."""

from __future__ import annotations

import json
from pathlib import Path

from server.main import generate_all


def _write_env_template(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# METADATA --- START",
                "description=Host variables",
                "required=true",
                "# METADATA --- END",
                "",
                "HOST_NAME=example",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_project_readme(path: Path) -> None:
    path.write_text(
        """---
author: Test Author
project_name: Test Project
project_description: Example description
project_source: https://github.com/test/project
stable_images:
  - test:1.0.0
date: 2026-04-26
last_updated: 2026-04-26
supported_architecture:
    - x86_64
    - arm64
ready_to_deploy: true
---
# Test Project
""",
        encoding="utf-8",
    )


def test_generate_all_writes_env_projects_meta_in_one_call(tmp_path: Path) -> None:
    env_dir = tmp_path / "00.env"
    env_dir.mkdir(parents=True)
    _write_env_template(env_dir / "host.env.template")

    project_dir = tmp_path / "01.test-project"
    project_dir.mkdir(parents=True)
    (project_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (project_dir / ".env.template").write_text("EXAMPLE=1\n", encoding="utf-8")
    _write_project_readme(project_dir / "readme.md")

    payload = generate_all(tmp_path)

    api_dir = tmp_path / "00.api" / "v1"
    env_json = api_dir / "env.json"
    projects_json = api_dir / "projects.json"
    meta_json = api_dir / "meta.json"

    assert env_json.exists()
    assert projects_json.exists()
    assert meta_json.exists()

    assert len(payload["env"]) == 1
    assert len(payload["projects"]) == 1
    assert len(payload["meta"]) == 2

    projects_data = json.loads(projects_json.read_text(encoding="utf-8"))
    assert projects_data[0]["project_name"] == "Test Project"

    meta_data = json.loads(meta_json.read_text(encoding="utf-8"))
    file_names = sorted(item["file_name"] for item in meta_data)
    assert file_names == ["env.json", "projects.json"]
