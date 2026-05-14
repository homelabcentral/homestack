"""CLI tests for the show-secrets command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cli.cli import app
from models.projects import ProjectItem
from typer.testing import CliRunner
from utils.shared_pref import HostPreferences

runner = CliRunner()


def _host_prefs(install_dir: str) -> HostPreferences:
    return HostPreferences(
        username="testuser",
        uid=1000,
        gid=1000,
        docker_gid=999,
        architecture="x86_64",
        cpu_count=4,
        ram_mb=8192,
        install_dir=install_dir,
        install_dir_total_gb=100.0,
    )


def _project_item(**overrides) -> ProjectItem:
    defaults = {
        "project_index": 1,
        "project_name": "Demo Project",
        "dir_name": "99.demo-project",
        "compose": "docker-compose.yml",
        "env": ".env.template",
        "readme": "readme.md",
        "config_files": [],
        "required_env_files": [],
        "project_description": "Demo",
        "supported_architecture": ["amd64"],
        "ready_to_deploy": True,
    }
    defaults.update(overrides)
    return ProjectItem(**defaults)


def _write_project_files(base_install_dir: Path, project: ProjectItem) -> Path:
    project_dir = base_install_dir / "compose" / "demo-project"
    project_dir.mkdir(parents=True, exist_ok=True)

    (project_dir / project.env).write_text(
        "\n".join(
            [
                "APP_SECRET= # type=password | remember=true | description=App secret",
                "ADMIN_HASH= # type=bcrypthash | remember=false | description=Admin hash",
                "PUBLIC_URL= # type=string | remember=true | description=Not a secret",
                "",
            ]
        ),
        encoding="utf-8",
    )

    (project_dir / ".env").write_text(
        "\n".join(
            [
                "APP_SECRET=super-secret-value",
                "ADMIN_HASH=$2b$12$somebcryptvalue",
                "PUBLIC_URL=https://example.local",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return project_dir


def test_show_secrets_defaults_to_remember_true_only(tmp_path: Path) -> None:
    install_dir = tmp_path / "homestack"
    project = _project_item()
    _write_project_files(install_dir, project)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(str(install_dir))),
        patch("cli.cli._load_cached_projects", return_value=[project]),
    ):
        result = runner.invoke(app, ["show-secrets", "demo project"])

    assert result.exit_code == 0
    assert "APP_SECRET" in result.output
    assert "super-secret-value" in result.output
    assert "ADMIN_HASH" not in result.output
    assert "somebcryptvalue" not in result.output


def test_show_secrets_all_includes_remember_false(tmp_path: Path) -> None:
    install_dir = tmp_path / "homestack"
    project = _project_item()
    _write_project_files(install_dir, project)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(str(install_dir))),
        patch("cli.cli._load_cached_projects", return_value=[project]),
    ):
        result = runner.invoke(app, ["show-secrets", "demo project", "--all"])

    assert result.exit_code == 0
    assert "APP_SECRET" in result.output
    assert "ADMIN_HASH" in result.output
    assert "somebcryptvalue" in result.output


def test_show_secrets_keys_only_hides_values(tmp_path: Path) -> None:
    install_dir = tmp_path / "homestack"
    project = _project_item()
    _write_project_files(install_dir, project)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(str(install_dir))),
        patch("cli.cli._load_cached_projects", return_value=[project]),
    ):
        result = runner.invoke(app, ["show-secrets", "demo project", "--keys-only"])

    assert result.exit_code == 0
    assert "APP_SECRET" in result.output
    assert "super-secret-value" not in result.output
    assert "ADMIN_HASH" not in result.output


def test_show_secrets_keys_only_with_all_includes_remember_false(tmp_path: Path) -> None:
    install_dir = tmp_path / "homestack"
    project = _project_item()
    _write_project_files(install_dir, project)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(str(install_dir))),
        patch("cli.cli._load_cached_projects", return_value=[project]),
    ):
        result = runner.invoke(
            app,
            ["show-secrets", "demo project", "--keys-only", "--all"],
        )

    assert result.exit_code == 0
    assert "APP_SECRET" in result.output
    assert "ADMIN_HASH" in result.output
    assert "somebcryptvalue" not in result.output


def test_show_secrets_fails_when_local_env_missing(tmp_path: Path) -> None:
    install_dir = tmp_path / "homestack"
    project = _project_item()
    project_dir = install_dir / "compose" / "demo-project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / project.env).write_text(
        "APP_SECRET= # type=password | remember=true\n",
        encoding="utf-8",
    )

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(str(install_dir))),
        patch("cli.cli._load_cached_projects", return_value=[project]),
    ):
        result = runner.invoke(app, ["show-secrets", "demo project"])

    assert result.exit_code == 1
    assert "No local env file found" in result.output