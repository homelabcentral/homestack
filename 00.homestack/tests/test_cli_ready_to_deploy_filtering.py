"""Tests for ready_to_deploy filtering across all CLI commands."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from cli.cli import app
from models.projects import ProjectItem
from typer.testing import CliRunner
from utils.shared_pref import HostPreferences

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helper: Create host preferences for testing
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Fixtures: Mixed ready/non-ready projects
# ---------------------------------------------------------------------------


def _create_mock_project(
    project_index: int,
    project_name: str,
    dir_name: str,
    ready_to_deploy: bool = True,
) -> ProjectItem:
    """Helper to create a mock ProjectItem."""
    return ProjectItem(
        project_index=project_index,
        project_name=project_name,
        dir_name=dir_name,
        compose="docker-compose.yml",
        env=".env.template",
        readme="readme.md",
        description=f"Test project: {project_name}",
        project_description=f"Test project: {project_name}",
        author="Homelab Central",
        project_source="https://github.com/test/test",
        project_website="https://test.com",
        project_docs="https://test.com",
        project_status="Active",
        stable_images=["test/image:latest"],
        stable_versions=["1.0.0"],
        latest_images=["test/image:latest"],
        latest_versions=["latest"],
        warning="none",
        date="2026-05-12",
        last_updated="2026-05-12",
        required_env_files=["host.env", "network.env"],
        supported_architecture=["amd64", "arm64"],
        ready_to_deploy=ready_to_deploy,
        config_files=None,
        pre_install_steps=None,
        post_install_steps=None,
        post_setup_steps=None,
    )


MOCK_PROJECTS_MIXED = [
    _create_mock_project(1, "Pihole", "01.pihole", ready_to_deploy=True),
    _create_mock_project(2, "Traefik", "02.traefik", ready_to_deploy=True),
    _create_mock_project(3, "Incomplete Project", "03.incomplete", ready_to_deploy=False),
    _create_mock_project(4, "Homepage", "04.homepage", ready_to_deploy=True),
    _create_mock_project(5, "Beta Project", "05.beta", ready_to_deploy=False),
]

READY_COUNT = sum(1 for p in MOCK_PROJECTS_MIXED if p.ready_to_deploy)
NOT_READY_COUNT = len(MOCK_PROJECTS_MIXED) - READY_COUNT


# ---------------------------------------------------------------------------
# Test: list command filters to ready projects only
# ---------------------------------------------------------------------------


def test_list_shows_only_ready_projects(tmp_path: Path) -> None:
    """Test that 'homestack list' displays only ready_to_deploy projects."""
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    
    # Write mixed projects to cache
    projects_json = cache_dir / "projects.json"
    projects_json.write_text(
        json.dumps([asdict(p) for p in MOCK_PROJECTS_MIXED])
    )

    with patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)), \
         patch("cli.cli.settings") as mock_settings, \
         patch("cli.cli._refresh_projects_cache_silent"):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    # Should show ready projects
    assert "Pihole" in result.stdout
    assert "Traefik" in result.stdout
    assert "Homepage" in result.stdout
    # Should NOT show non-ready projects
    assert "Incomplete Project" not in result.stdout
    assert "Beta Project" not in result.stdout


def test_list_shows_ready_count(tmp_path: Path) -> None:
    """Test that list shows only ready projects (correct count)."""
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    
    projects_json = cache_dir / "projects.json"
    projects_json.write_text(
        json.dumps([asdict(p) for p in MOCK_PROJECTS_MIXED])
    )

    with patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)), \
         patch("cli.cli.settings") as mock_settings, \
         patch("cli.cli._refresh_projects_cache_silent"):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    # Verify ready projects are shown
    ready_projects = [p for p in MOCK_PROJECTS_MIXED if p.ready_to_deploy]
    assert len(ready_projects) == READY_COUNT
    for project in ready_projects:
        assert project.project_name in result.stdout


# ---------------------------------------------------------------------------
# Test: search command filters to ready projects only
# ---------------------------------------------------------------------------


def test_search_shows_only_ready_projects(tmp_path: Path) -> None:
    """Test that 'homestack search' only returns ready projects."""
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    
    projects_json = cache_dir / "projects.json"
    projects_json.write_text(
        json.dumps([asdict(p) for p in MOCK_PROJECTS_MIXED])
    )

    with patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)), \
         patch("cli.cli.settings") as mock_settings, \
         patch("cli.cli._refresh_projects_cache_silent"):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["search", "project"])

    assert result.exit_code == 0
    # Should show ready projects matching search
    assert "Pihole" in result.stdout or "Homepage" in result.stdout
    # Should NOT show non-ready projects even if they match
    assert "Incomplete Project" not in result.stdout
    assert "Beta Project" not in result.stdout


def test_search_for_ready_project(tmp_path: Path) -> None:
    """Test searching for a specific ready project."""
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    
    projects_json = cache_dir / "projects.json"
    projects_json.write_text(
        json.dumps([asdict(p) for p in MOCK_PROJECTS_MIXED])
    )

    with patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)), \
         patch("cli.cli.settings") as mock_settings, \
         patch("cli.cli._refresh_projects_cache_silent"):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["search", "pihole"])

    assert result.exit_code == 0
    assert "Pihole" in result.stdout


def test_search_for_non_ready_project_returns_nothing(tmp_path: Path) -> None:
    """Test searching for non-ready project returns no results."""
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    
    projects_json = cache_dir / "projects.json"
    projects_json.write_text(
        json.dumps([asdict(p) for p in MOCK_PROJECTS_MIXED])
    )

    with patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)), \
         patch("cli.cli.settings") as mock_settings, \
         patch("cli.cli._refresh_projects_cache_silent"):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["search", "incomplete"])

    # Should return 0 results since "Incomplete Project" is not ready
    assert result.exit_code == 0
    assert "Incomplete Project" not in result.stdout


# ---------------------------------------------------------------------------
# Test: info command filters to ready projects only
# ---------------------------------------------------------------------------


def test_info_shows_ready_project(tmp_path: Path) -> None:
    """Test that 'homestack info' can show info for ready projects."""
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    
    projects_json = cache_dir / "projects.json"
    projects_json.write_text(
        json.dumps([asdict(p) for p in MOCK_PROJECTS_MIXED])
    )

    pihole_project = next(p for p in MOCK_PROJECTS_MIXED if p.project_name == "Pihole")

    with patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)), \
         patch("cli.cli.settings") as mock_settings, \
         patch("cli.cli._refresh_projects_cache_silent"), \
         patch("cli.cli._find_project", return_value=pihole_project), \
         patch("cli.cli._print_info_readme"):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["info", "pihole"])

    assert result.exit_code == 0


def test_info_cannot_show_non_ready_project(tmp_path: Path) -> None:
    """Test that 'homestack info' cannot show info for non-ready projects."""
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    
    projects_json = cache_dir / "projects.json"
    projects_json.write_text(
        json.dumps([asdict(p) for p in MOCK_PROJECTS_MIXED])
    )

    with patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)), \
         patch("cli.cli.settings") as mock_settings, \
         patch("cli.cli._refresh_projects_cache_silent"):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["info", "incomplete"])

    # Should fail because project not found in filtered list
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Test: pull command filters to ready projects only
# ---------------------------------------------------------------------------


def test_pull_cannot_select_non_ready_project(tmp_path: Path) -> None:
    """Test that pull command cannot select non-ready projects."""
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    
    projects_json = cache_dir / "projects.json"
    projects_json.write_text(
        json.dumps([asdict(p) for p in MOCK_PROJECTS_MIXED])
    )

    with patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)), \
         patch("cli.cli.settings") as mock_settings, \
         patch("cli.cli._refresh_projects_cache_silent"):
        mock_settings.cache_api_dir = cache_dir
        # Try to pull non-ready project - should fail
        result = runner.invoke(app, ["pull", "incomplete"])

    # Should fail because project not found in filtered list
    assert result.exit_code != 0


def test_pull_can_select_ready_project(tmp_path: Path) -> None:
    """Test that pull command can select ready projects."""
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    
    projects_json = cache_dir / "projects.json"
    projects_json.write_text(
        json.dumps([asdict(p) for p in MOCK_PROJECTS_MIXED])
    )

    with patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)), \
         patch("cli.cli.settings") as mock_settings, \
         patch("cli.cli._refresh_projects_cache_silent"), \
         patch("cli.cli._pull_project_files") as mock_pull:
        mock_settings.cache_api_dir = cache_dir
        mock_pull.return_value = (cache_dir / "pihole", 1, 0)
        
        # Try to pull ready project
        result = runner.invoke(app, ["pull", "pihole"])

    # Should succeed in finding the project (actual file operations mocked)
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Test: deploy command filters to ready projects only
# ---------------------------------------------------------------------------


def test_deploy_cannot_select_non_ready_project(tmp_path: Path) -> None:
    """Test that deploy command cannot select non-ready projects."""
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    
    projects_json = cache_dir / "projects.json"
    projects_json.write_text(
        json.dumps([asdict(p) for p in MOCK_PROJECTS_MIXED])
    )

    with patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)), \
         patch("cli.cli.settings") as mock_settings, \
         patch("cli.cli._refresh_projects_cache_silent"):
        mock_settings.cache_api_dir = cache_dir
        # Try to deploy non-ready project
        result = runner.invoke(app, ["deploy", "beta"])

    # Should fail because project not found in filtered list
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Test: upgrade command filters to ready projects only
# ---------------------------------------------------------------------------


def test_upgrade_cannot_select_non_ready_project(tmp_path: Path) -> None:
    """Test that upgrade command cannot select non-ready projects."""
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    
    projects_json = cache_dir / "projects.json"
    projects_json.write_text(
        json.dumps([asdict(p) for p in MOCK_PROJECTS_MIXED])
    )

    with patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)), \
         patch("cli.cli.settings") as mock_settings, \
         patch("cli.cli._refresh_projects_cache_silent"):
        mock_settings.cache_api_dir = cache_dir
        # Try to upgrade non-ready project
        result = runner.invoke(app, ["upgrade", "beta"])

    # Should fail because project not found in filtered list
    assert result.exit_code != 0


def test_upgrade_can_select_ready_project(tmp_path: Path) -> None:
    """Test that upgrade command can select ready projects."""
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    
    projects_json = cache_dir / "projects.json"
    projects_json.write_text(
        json.dumps([asdict(p) for p in MOCK_PROJECTS_MIXED])
    )

    pihole_project = next(p for p in MOCK_PROJECTS_MIXED if p.project_name == "Pihole")

    with patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)), \
         patch("cli.cli.settings") as mock_settings, \
         patch("cli.cli._refresh_projects_cache_silent"), \
         patch("cli.cli._find_project", return_value=pihole_project), \
         patch("cli.cli._print_info_readme"):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["upgrade", "pihole"])

    # Should succeed in finding the project
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Test: start/stop/restart/remove/recreate allow non-ready installed projects
# ---------------------------------------------------------------------------


def test_start_allows_non_ready_installed_project(tmp_path: Path) -> None:
    """Test that start command works with non-ready projects if already installed."""
    install_dir = tmp_path / "homestack"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    
    projects_json = cache_dir / "projects.json"
    projects_json.write_text(
        json.dumps([asdict(p) for p in MOCK_PROJECTS_MIXED])
    )

    # Create the installed project directory structure using correct slug name
    compose_dir = install_dir / "compose"
    project_dir = compose_dir / "incomplete-project"
    project_dir.mkdir(parents=True)
    (project_dir / "docker-compose.yml").write_text("version: '3'")
    (project_dir / ".env").write_text("TEST=value")
    # Create required shared env files in compose_dir/00.env/
    env_dir = compose_dir / "00.env"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / "host.env").write_text("HOST=value")
    (env_dir / "network.env").write_text("NETWORK=value")

    incomplete_project = next(p for p in MOCK_PROJECTS_MIXED if p.project_name == "Incomplete Project")

    with patch("cli.cli._require_init_or_exit", return_value=_host_prefs(str(install_dir))), \
         patch("cli.cli.settings") as mock_settings, \
         patch("cli.cli._refresh_projects_cache_silent"), \
         patch("cli.cli._load_cached_projects", return_value=MOCK_PROJECTS_MIXED), \
         patch("cli.cli.validate_compose_config"), \
         patch("cli.cli.start_project_stack"), \
         patch("cli.cli._print_info_readme"), \
         patch("cli.cli._validate_project_compose_config"):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["start", "incomplete"])

    # Should succeed because start uses filter_ready=False, allowing non-ready installed projects
    assert result.exit_code == 0


def test_start_rejects_non_installed_non_ready_project(tmp_path: Path) -> None:
    """Test that start command rejects non-ready projects that aren't installed."""
    install_dir = tmp_path / "homestack"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    
    projects_json = cache_dir / "projects.json"
    projects_json.write_text(
        json.dumps([asdict(p) for p in MOCK_PROJECTS_MIXED])
    )

    with patch("cli.cli._require_init_or_exit", return_value=_host_prefs(str(install_dir))), \
         patch("cli.cli.settings") as mock_settings, \
         patch("cli.cli._refresh_projects_cache_silent"):
        mock_settings.cache_api_dir = cache_dir
        # Try to start non-ready project that isn't installed
        result = runner.invoke(app, ["start", "incomplete"])

    # Should fail because project not installed
    assert result.exit_code != 0
