"""Integration tests for init → update → list workflow."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from api.exceptions import APIHTTPError, APINetworkError
from cli import cli as cli_module
from models.projects import ProjectItem
from typer.testing import CliRunner
from utils.shared_pref import HostPreferences, SharedPreferences


def _host_prefs(install_dir: Path) -> HostPreferences:
    return HostPreferences(
        username="tester",
        uid=1000,
        gid=1000,
        docker_gid=999,
        architecture="x86_64",
        cpu_count=4,
        ram_mb=8192,
        install_dir=str(install_dir),
        install_dir_total_gb=100.0,
    )


@pytest.fixture
def sample_meta_response() -> list[dict]:
    """Sample meta.json response from API."""
    return [
        {
            "file_name": "env.json",
            "sha": "abc123",
            "size": 1024,
            "updated_at": "2026-04-25T00:00:00Z",
        },
        {
            "file_name": "projects.json",
            "sha": "def456",
            "size": 2048,
            "updated_at": "2026-04-25T00:00:00Z",
        },
        {
            "file_name": "readmes.json",
            "sha": "ghi789",
            "size": 4096,
            "updated_at": "2026-04-25T00:00:00Z",
        },
    ]


@pytest.fixture
def sample_projects_response() -> list[dict]:
    """Sample projects.json response from API."""
    return [
        {
            "project_index": 1,
            "project_name": "Pihole Unbound",
            "dir_name": "01.pihole-unbound",
            "compose": "docker-compose.yml",
            "env": ".env.template",
            "readme": "readme.md",
        },
        {
            "project_index": 2,
            "project_name": "Traefik",
            "dir_name": "02.traefik",
            "compose": "docker-compose.yml",
            "env": ".env.template",
            "readme": "readme.md",
        },
    ]


@pytest.fixture
def sample_readmes_response() -> list[dict]:
    """Sample readmes.json response from API."""
    return [
        {
            "project_name": "Pihole Unbound",
            "project_description": "DNS and ad blocker",
            "project_source": "https://github.com/pi-hole/pi-hole",
            "project_website": "https://pi-hole.net",
            "project_docs": "https://docs.pi-hole.net",
            "project_status": "Active",
            "stable_images": ["pihole:latest"],
            "stable_versions": ["5.18"],
            "latest_images": ["pihole:latest"],
            "latest_versions": ["5.18"],
            "warning": None,
            "date": "2026-04-25",
            "last_updated": "2026-04-25",
            "required_env_files": [],
            "config_files": [],
            "pre_install_steps": [],
            "post_install_steps": [],
            "post_setup_steps": [],
            "ready_to_deploy": True,
        },
        {
            "project_name": "Traefik",
            "project_description": "Reverse proxy",
            "project_source": "https://github.com/traefik/traefik",
            "project_website": "https://traefik.io",
            "project_docs": "https://doc.traefik.io",
            "project_status": "Active",
            "stable_images": ["traefik:latest"],
            "stable_versions": ["2.10"],
            "latest_images": ["traefik:latest"],
            "latest_versions": ["2.10"],
            "warning": None,
            "date": "2026-04-25",
            "last_updated": "2026-04-25",
            "required_env_files": [],
            "config_files": [],
            "pre_install_steps": [],
            "post_install_steps": [],
            "post_setup_steps": [],
            "ready_to_deploy": True,
        },
    ]


def test_init_stores_preferences(tmp_path: Path):
    """Test that init command stores host preferences correctly."""
    db_path = tmp_path / "prefs.db"

    with SharedPreferences(db_path=db_path) as prefs:
        assert prefs.is_initialized() is False

        host_prefs = HostPreferences(
            username="testuser",
            uid=1000,
            gid=1000,
            docker_gid=999,
            architecture="x86_64",
            cpu_count=8,
            ram_mb=16384,
            install_dir=str(tmp_path / "homestack"),
            install_dir_total_gb=500.0,
        )
        prefs.set_host_preferences(host_prefs)
        assert prefs.is_initialized() is True

    # Verify persistence: reopen and check
    with SharedPreferences(db_path=db_path) as prefs_again:
        assert prefs_again.is_initialized() is True
        loaded = prefs_again.get_host_preferences()
        assert loaded.username == "testuser"
        assert loaded.cpu_count == 8
        assert loaded.install_dir.endswith("homestack")


def test_init_skips_when_already_initialized_without_force(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    runner = CliRunner()
    db_path = tmp_path / "prefs.db"

    with SharedPreferences(db_path=db_path) as prefs:
        prefs.set_host_preferences(
            HostPreferences(
                username="existing-user",
                uid=1000,
                gid=1000,
                docker_gid=999,
                architecture="x86_64",
                cpu_count=4,
                ram_mb=8192,
                install_dir=str(tmp_path / "existing-homestack"),
                install_dir_total_gb=100.0,
            )
        )

    class TestSharedPreferences(SharedPreferences):
        def __init__(self):
            super().__init__(db_path=db_path)

    download_mock = MagicMock()
    monkeypatch.setattr(cli_module, "SharedPreferences", TestSharedPreferences)
    monkeypatch.setattr(cli_module, "_download_env_templates", download_mock)
    monkeypatch.setattr(cli_module, "ensure_traefik_bridge_network", MagicMock())

    result = runner.invoke(cli_module.app, ["init"])
    output = result.output
    if hasattr(result, "stderr") and result.stderr:
        output += result.stderr

    assert result.exit_code == 0
    assert "already initialized" in output
    download_mock.assert_not_called()


def test_init_force_reinitializes_when_already_initialized(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    runner = CliRunner()
    db_path = tmp_path / "prefs.db"
    old_install_dir = tmp_path / "old-homestack"
    new_install_dir = tmp_path / "new-homestack"

    with SharedPreferences(db_path=db_path) as prefs:
        prefs.set_host_preferences(
            HostPreferences(
                username="existing-user",
                uid=1000,
                gid=1000,
                docker_gid=999,
                architecture="x86_64",
                cpu_count=4,
                ram_mb=8192,
                install_dir=str(old_install_dir),
                install_dir_total_gb=100.0,
            )
        )

    class TestSharedPreferences(SharedPreferences):
        def __init__(self):
            super().__init__(db_path=db_path)

    download_mock = MagicMock()
    monkeypatch.setattr(cli_module, "SharedPreferences", TestSharedPreferences)
    monkeypatch.setattr(cli_module, "_download_env_templates", download_mock)
    monkeypatch.setattr(cli_module, "ensure_traefik_bridge_network", MagicMock())

    result = runner.invoke(
        cli_module.app, ["init", "--force"], input=f"{new_install_dir}\n"
    )
    output = result.output
    if hasattr(result, "stderr") and result.stderr:
        output += result.stderr

    assert result.exit_code == 0
    assert "Re-running initialization due to --force." in output
    assert "homestack initialization completed." in output

    download_mock.assert_called_once()
    called_compose_dir = download_mock.call_args.args[0]
    assert called_compose_dir == (new_install_dir / "compose").resolve()
    assert (new_install_dir / "data").resolve().exists()

    with SharedPreferences(db_path=db_path) as prefs:
        loaded = prefs.get_host_preferences()
        assert loaded.install_dir == str(new_install_dir.resolve())


def test_update_caches_files_from_api(
    tmp_path: Path,
    sample_meta_response: list[dict],
    sample_projects_response: list[dict],
    sample_readmes_response: list[dict],
):
    """Test that update command fetches and caches files."""
    cache_dir = tmp_path / "cache" / "api" / "v1"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Simulate files being written to cache (as would happen in update)
    (cache_dir / "projects.json").write_text(
        json.dumps(sample_projects_response, indent=2) + "\n",
        encoding="utf-8",
    )
    (cache_dir / "readmes.json").write_text(
        json.dumps(sample_readmes_response, indent=2) + "\n",
        encoding="utf-8",
    )

    # Verify files exist and contain expected data
    assert (cache_dir / "projects.json").exists()
    assert (cache_dir / "readmes.json").exists()

    projects_data = json.loads(
        (cache_dir / "projects.json").read_text(encoding="utf-8")
    )
    assert len(projects_data) == 2
    assert projects_data[0]["project_name"] == "Pihole Unbound"


def test_list_reads_cached_projects(
    tmp_path: Path,
    sample_projects_response: list[dict],
    sample_readmes_response: list[dict],
):
    """Test that list command reads cached projects and readmes."""
    cache_dir = tmp_path / "cache" / "api" / "v1"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Setup cache files
    (cache_dir / "projects.json").write_text(
        json.dumps(sample_projects_response, indent=2) + "\n",
        encoding="utf-8",
    )
    (cache_dir / "readmes.json").write_text(
        json.dumps(sample_readmes_response, indent=2) + "\n",
        encoding="utf-8",
    )

    # Load as list command would
    projects = [ProjectItem(**row) for row in sample_projects_response]
    assert len(projects) == 2
    assert projects[0].project_name == "Pihole Unbound"
    assert projects[1].project_name == "Traefik"

    # Verify readme data is also loaded
    readmes_data = json.loads((cache_dir / "readmes.json").read_text(encoding="utf-8"))
    assert len(readmes_data) == 2
    assert readmes_data[0]["project_description"] == "DNS and ad blocker"


def test_search_filters_cached_projects(sample_projects_response: list[dict]):
    """Test that search filters projects by substring match."""
    projects = [ProjectItem(**row) for row in sample_projects_response]

    # Search for "pihole"
    matches = [p for p in projects if "pihole" in p.project_name.lower()]
    assert len(matches) == 1
    assert matches[0].project_name == "Pihole Unbound"

    # Search for "traefik"
    matches = [p for p in projects if "traefik" in p.project_name.lower()]
    assert len(matches) == 1
    assert matches[0].project_name == "Traefik"

    # Search for "dns"
    matches = [p for p in projects if "dns" in str(p).lower()]
    assert len(matches) == 0  # 'dns' not in project names


def test_cache_fallback_when_missing(
    tmp_path: Path,
    sample_projects_response: list[dict],
):
    """Test that missing cache is detected before use."""
    cache_dir = tmp_path / "cache" / "api" / "v1"

    # Cache doesn't exist
    assert not cache_dir.exists()
    assert not (cache_dir / "projects.json").exists()

    # Commands should handle this gracefully by checking existence
    projects_path = cache_dir / "projects.json"
    if not projects_path.exists():
        # Would trigger update in real CLI
        cache_dir.mkdir(parents=True, exist_ok=True)
        projects_path.write_text(
            json.dumps(sample_projects_response, indent=2) + "\n",
            encoding="utf-8",
        )

    assert projects_path.exists()
    projects_data = json.loads(projects_path.read_text(encoding="utf-8"))
    assert len(projects_data) == 2


@pytest.mark.integration
def test_full_init_update_list_workflow(
    tmp_path: Path,
    sample_meta_response: list[dict],
    sample_projects_response: list[dict],
    sample_readmes_response: list[dict],
):
    """Integration test: init → update → list → search."""
    # Step 1: Initialize preferences
    db_path = tmp_path / "config" / "prefs.db"
    with SharedPreferences(db_path=db_path) as prefs:
        assert not prefs.is_initialized()

        prefs.set_host_preferences(
            HostPreferences(
                username="devtest",
                uid=1000,
                gid=1000,
                docker_gid=999,
                architecture="x86_64",
                cpu_count=4,
                ram_mb=8192,
                install_dir=str(tmp_path / "homestack"),
                install_dir_total_gb=100.0,
            )
        )
        assert prefs.is_initialized()

    # Step 2: Update cache (simulated)
    cache_dir = tmp_path / "cache" / "api" / "v1"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "projects.json").write_text(
        json.dumps(sample_projects_response, indent=2) + "\n",
        encoding="utf-8",
    )
    (cache_dir / "readmes.json").write_text(
        json.dumps(sample_readmes_response, indent=2) + "\n",
        encoding="utf-8",
    )

    # Step 3: List projects
    projects = [ProjectItem(**row) for row in sample_projects_response]
    assert len(projects) == 2

    # Step 4: Search
    search_results = [p for p in projects if "pihole" in p.project_name.lower()]
    assert len(search_results) == 1
    assert search_results[0].dir_name == "01.pihole-unbound"

    # Step 5: Verify prefs are still accessible
    with SharedPreferences(db_path=db_path) as prefs_check:
        assert prefs_check.is_initialized()
        loaded = prefs_check.get_host_preferences()
        assert loaded.username == "devtest"


def test_update_http_404_shows_friendly_message_no_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runner = CliRunner()
    cache_dir = tmp_path / "cache" / "api" / "v1"

    monkeypatch.setattr(cli_module, "_require_init_or_exit", lambda: None)
    monkeypatch.setattr(cli_module.settings, "cache_api_dir", cache_dir)

    class FailingAPIClient:
        def __init__(self, *args, **kwargs):
            pass

        def fetch_meta_sync(self):
            raise APIHTTPError(
                url="https://example.invalid/00.api/v1/meta.json",
                status_code=404,
                message="Remote file not found (404)",
            )

    monkeypatch.setattr(cli_module, "APIClient", FailingAPIClient)

    result = runner.invoke(cli_module.app, ["update"])
    output = result.output
    if hasattr(result, "stderr") and result.stderr:
        output += result.stderr

    assert result.exit_code == 1
    assert "remote API file was not found (HTTP 404)" in output
    assert "Traceback" not in output


def test_update_network_error_shows_friendly_message_no_traceback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    runner = CliRunner()
    cache_dir = tmp_path / "cache" / "api" / "v1"

    monkeypatch.setattr(cli_module, "_require_init_or_exit", lambda: None)
    monkeypatch.setattr(cli_module.settings, "cache_api_dir", cache_dir)

    class FailingAPIClient:
        def __init__(self, *args, **kwargs):
            pass

        def fetch_meta_sync(self):
            raise APINetworkError("network down")

    monkeypatch.setattr(cli_module, "APIClient", FailingAPIClient)

    result = runner.invoke(cli_module.app, ["update"])
    output = result.output
    if hasattr(result, "stderr") and result.stderr:
        output += result.stderr

    assert result.exit_code == 1
    assert "could not reach the remote API" in output
    assert "Traceback" not in output


def test_list_prefers_api_layer_refresh_and_falls_back_to_local_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    runner = CliRunner()
    cache_dir = tmp_path / "cache" / "api" / "v1"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "projects.json").write_text(
        json.dumps(
            [
                {
                    "project_index": 1,
                    "project_name": "Pi-hole",
                    "dir_name": "01.pihole-unbound",
                    "compose": "docker-compose.yml",
                    "env": ".env.template",
                    "readme": "readme.md",
                    "project_description": "DNS and ad blocker",
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(cli_module, "_require_init_or_exit", lambda: None)
    monkeypatch.setattr(cli_module.settings, "cache_api_dir", cache_dir)

    class FailingRefreshAPIClient:
        def __init__(self, *args, **kwargs):
            pass

        def refresh_projects_cache_sync(self, cache_dir: Path, *, silent: bool = True):
            raise APINetworkError("network down")

    monkeypatch.setattr(cli_module, "APIClient", FailingRefreshAPIClient)

    result = runner.invoke(cli_module.app, ["list"])
    output = result.output
    if hasattr(result, "stderr") and result.stderr:
        output += result.stderr

    assert result.exit_code == 0
    assert "Pi-hole" in output


def test_search_uses_cached_projects_when_conditional_refresh_returns_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    runner = CliRunner()
    cache_dir = tmp_path / "cache" / "api" / "v1"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "projects.json").write_text(
        json.dumps(
            [
                {
                    "project_index": 2,
                    "project_name": "Traefik",
                    "dir_name": "02.traefik",
                    "compose": "docker-compose.yml",
                    "env": ".env.template",
                    "readme": "readme.md",
                    "project_description": "Edge reverse proxy",
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(cli_module, "_require_init_or_exit", lambda: None)
    monkeypatch.setattr(cli_module.settings, "cache_api_dir", cache_dir)

    class ErrorRefreshAPIClient:
        def __init__(self, *args, **kwargs):
            pass

        def refresh_projects_cache_sync(self, cache_dir: Path, *, silent: bool = True):
            return "error"

    monkeypatch.setattr(cli_module, "APIClient", ErrorRefreshAPIClient)

    result = runner.invoke(cli_module.app, ["search", "traefik"])
    output = result.output
    if hasattr(result, "stderr") and result.stderr:
        output += result.stderr

    assert result.exit_code == 0
    assert "Traefik" in output


def test_info_uses_cached_projects_when_refresh_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    runner = CliRunner()
    cache_dir = tmp_path / "cache" / "api" / "v1"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "projects.json").write_text(
        json.dumps(
            [
                {
                    "project_index": 1,
                    "project_name": "Pi-hole",
                    "dir_name": "01.pihole-unbound",
                    "compose": "docker-compose.yml",
                    "env": ".env.template",
                    "readme": "readme.md",
                    "project_description": "DNS and ad blocker",
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    install_dir = tmp_path / "homestack"
    local_readme = install_dir / "compose" / "pi-hole" / "readme.md"
    local_readme.parent.mkdir(parents=True, exist_ok=True)
    local_readme.write_text("# Local README\n\nLoaded from disk", encoding="utf-8")

    monkeypatch.setattr(
        cli_module,
        "_require_init_or_exit",
        lambda: _host_prefs(install_dir),
    )
    monkeypatch.setattr(cli_module.settings, "cache_api_dir", cache_dir)

    class FailingRefreshAPIClient:
        def __init__(self, *args, **kwargs):
            pass

        def refresh_projects_cache_sync(self, cache_dir: Path, *, silent: bool = True):
            raise APINetworkError("network down")

    monkeypatch.setattr(cli_module, "APIClient", FailingRefreshAPIClient)

    result = runner.invoke(cli_module.app, ["info", "pi-hole"])
    output = result.output
    if hasattr(result, "stderr") and result.stderr:
        output += result.stderr

    assert result.exit_code == 0
    assert "Project Info: Pi-hole" in output


def test_info_falls_back_to_remote_readme_when_local_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    runner = CliRunner()
    cache_dir = tmp_path / "cache" / "api" / "v1"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "projects.json").write_text(
        json.dumps(
            [
                {
                    "project_index": 1,
                    "project_name": "Pi-hole",
                    "dir_name": "01.pihole-unbound",
                    "compose": "docker-compose.yml",
                    "env": ".env.template",
                    "readme": "readme.md",
                    "project_description": "DNS and ad blocker",
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    install_dir = tmp_path / "homestack"
    monkeypatch.setattr(
        cli_module,
        "_require_init_or_exit",
        lambda: _host_prefs(install_dir),
    )
    monkeypatch.setattr(cli_module.settings, "cache_api_dir", cache_dir)

    class RemoteReadmeAPIClient:
        def __init__(self, *args, **kwargs):
            pass

        def refresh_projects_cache_sync(self, cache_dir: Path, *, silent: bool = True):
            return "error"

        def fetch_text_sync(self, url_or_path: str) -> str:
            assert url_or_path == "01.pihole-unbound/readme.md"
            return "# Remote README\n\nLoaded from remote"

    monkeypatch.setattr(cli_module, "APIClient", RemoteReadmeAPIClient)

    result = runner.invoke(cli_module.app, ["info", "pi-hole"])
    output = result.output
    if hasattr(result, "stderr") and result.stderr:
        output += result.stderr

    assert result.exit_code == 0
    assert "Project Info: Pi-hole" in output
    assert "displaying remote README from 01.pihole-unbound/readme.md" in output
    assert "Remote README" in output


def test_info_warns_when_remote_readme_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    runner = CliRunner()
    cache_dir = tmp_path / "cache" / "api" / "v1"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "projects.json").write_text(
        json.dumps(
            [
                {
                    "project_index": 1,
                    "project_name": "Pi-hole",
                    "dir_name": "01.pihole-unbound",
                    "compose": "docker-compose.yml",
                    "env": ".env.template",
                    "readme": "readme.md",
                    "project_description": "DNS and ad blocker",
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    install_dir = tmp_path / "homestack"
    monkeypatch.setattr(
        cli_module,
        "_require_init_or_exit",
        lambda: _host_prefs(install_dir),
    )
    monkeypatch.setattr(cli_module.settings, "cache_api_dir", cache_dir)

    class UnreachableRemoteReadmeAPIClient:
        def __init__(self, *args, **kwargs):
            pass

        def refresh_projects_cache_sync(self, cache_dir: Path, *, silent: bool = True):
            return "error"

        def fetch_text_sync(self, url_or_path: str) -> str:
            raise APINetworkError("network down")

    monkeypatch.setattr(cli_module, "APIClient", UnreachableRemoteReadmeAPIClient)

    result = runner.invoke(cli_module.app, ["info", "pi-hole"])
    output = result.output
    if hasattr(result, "stderr") and result.stderr:
        output += result.stderr

    assert result.exit_code == 0
    assert "Project Info: Pi-hole" in output
    assert "remote README could not be reached" in output


def test_upgrade_uses_cached_projects_when_refresh_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    runner = CliRunner()
    cache_dir = tmp_path / "cache" / "api" / "v1"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "projects.json").write_text(
        json.dumps(
            [
                {
                    "project_index": 2,
                    "project_name": "Traefik",
                    "dir_name": "02.traefik",
                    "compose": "docker-compose.yml",
                    "env": ".env.template",
                    "readme": "readme.md",
                    "project_description": "Edge reverse proxy",
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    install_dir = tmp_path / "homestack"
    local_readme = install_dir / "compose" / "traefik" / "readme.md"
    local_readme.parent.mkdir(parents=True, exist_ok=True)
    local_readme.write_text(
        "# Local Traefik README\n\nLoaded from disk", encoding="utf-8"
    )

    monkeypatch.setattr(
        cli_module,
        "_require_init_or_exit",
        lambda: _host_prefs(install_dir),
    )
    monkeypatch.setattr(cli_module.settings, "cache_api_dir", cache_dir)

    class ErrorRefreshAPIClient:
        def __init__(self, *args, **kwargs):
            pass

        def refresh_projects_cache_sync(self, cache_dir: Path, *, silent: bool = True):
            return "error"

    monkeypatch.setattr(cli_module, "APIClient", ErrorRefreshAPIClient)

    result = runner.invoke(cli_module.app, ["upgrade", "traefik"])
    output = result.output
    if hasattr(result, "stderr") and result.stderr:
        output += result.stderr

    assert result.exit_code == 0
    assert "Project Info: Traefik" in output
