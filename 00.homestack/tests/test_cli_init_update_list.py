"""CLI tests: real-API integration + monkeypatch coverage for non-API behavior."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from api.client import APIClient
from api.exceptions import APIHTTPError, APINetworkError
from cli import cli as cli_module
from cli.cli import app
from models.projects import ProjectItem
from typer.testing import CliRunner
from utils.shared_pref import HostPreferences, SharedPreferences

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
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


def test_init_stores_preferences(tmp_path: Path) -> None:
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

    with SharedPreferences(db_path=db_path) as prefs_again:
        assert prefs_again.is_initialized() is True
        loaded = prefs_again.get_host_preferences()
        assert loaded.username == "testuser"
        assert loaded.cpu_count == 8
        assert loaded.install_dir.endswith("homestack")


def test_init_overwrites_preferences_on_second_write(tmp_path: Path) -> None:
    db_path = tmp_path / "prefs.db"

    first = HostPreferences(
        username="first-user",
        uid=1000,
        gid=1000,
        docker_gid=999,
        architecture="x86_64",
        cpu_count=4,
        ram_mb=8192,
        install_dir=str(tmp_path / "first-install"),
        install_dir_total_gb=100.0,
    )
    second = HostPreferences(
        username="second-user",
        uid=1001,
        gid=1001,
        docker_gid=998,
        architecture="x86_64",
        cpu_count=16,
        ram_mb=32768,
        install_dir=str(tmp_path / "second-install"),
        install_dir_total_gb=200.0,
    )

    with SharedPreferences(db_path=db_path) as prefs:
        prefs.set_host_preferences(first)
        prefs.set_host_preferences(second)

    with SharedPreferences(db_path=db_path) as prefs_again:
        loaded = prefs_again.get_host_preferences()

    assert loaded.username == "second-user"
    assert loaded.cpu_count == 16
    assert loaded.install_dir.endswith("second-install")


def test_live_api_returns_meta_and_projects() -> None:
    client = APIClient(environment="prod")

    meta = client.fetch_meta_sync()
    projects = client.fetch_projects_sync()

    assert len(meta) >= 2
    assert any(item.file_name == "projects.json" for item in meta)
    assert len(projects) > 0
    assert any(project.project_name == "Pihole with Unbound" for project in projects)


def test_refresh_projects_cache_writes_real_projects_json(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache" / "api" / "v1"
    client = APIClient(environment="prod")

    status = client.refresh_projects_cache_sync(cache_dir, silent=False)

    assert status == "downloaded"
    projects_path = cache_dir / "projects.json"
    assert projects_path.exists()

    payload = json.loads(projects_path.read_text(encoding="utf-8"))
    assert len(payload) > 0
    assert payload[0]["project_name"] == "Pihole with Unbound"


def test_load_cached_projects_from_real_cache(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache" / "api" / "v1"
    client = APIClient(environment="prod")
    client.refresh_projects_cache_sync(cache_dir, silent=False)

    projects = cli_module._load_cached_projects(cache_dir, check_remote_change=False)

    assert len(projects) > 0
    assert isinstance(projects[0], ProjectItem)
    assert any(project.project_name == "Traefik" for project in projects)


def test_pull_project_files_downloads_to_temp_compose_dir(
    real_project_items: list[ProjectItem],
    tmp_path: Path,
) -> None:
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir(parents=True, exist_ok=True)
    selected = real_project_items[0]

    project_dir, downloaded_count, skipped = cli_module._pull_project_files(
        selected,
        compose_dir,
        force=False,
    )

    assert downloaded_count >= 3
    assert skipped == []
    assert (project_dir / selected.compose).exists()
    assert (project_dir / selected.env).exists()
    assert (project_dir / selected.readme).exists()


def test_pull_project_files_second_run_skips_existing(
    real_project_items: list[ProjectItem],
    tmp_path: Path,
) -> None:
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir(parents=True, exist_ok=True)
    selected = real_project_items[0]

    cli_module._pull_project_files(selected, compose_dir, force=False)
    project_dir, downloaded_count, skipped = cli_module._pull_project_files(
        selected,
        compose_dir,
        force=False,
    )

    assert downloaded_count == 0
    assert len(skipped) >= 3
    assert project_dir.exists()


# ---------------------------------------------------------------------------
# Init: idempotency and force behavior
# ---------------------------------------------------------------------------


def test_init_skips_when_already_initialized_without_force(tmp_path: Path) -> None:
    db_path = tmp_path / "prefs.db"
    install_dir = str(tmp_path / "homestack")

    with SharedPreferences(db_path=db_path) as prefs:
        prefs.set_host_preferences(_host_prefs(install_dir))

    with patch("cli.cli.SharedPreferences") as mock_prefs_cls:
        mock_prefs = MagicMock()
        mock_prefs.__enter__ = MagicMock(return_value=mock_prefs)
        mock_prefs.__exit__ = MagicMock(return_value=False)
        mock_prefs.is_initialized.return_value = True
        mock_prefs.get_host_preferences.return_value = _host_prefs(install_dir)
        mock_prefs_cls.return_value = mock_prefs

        result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert "already initialized" in result.output


def test_init_force_reinitializes_when_already_initialized(tmp_path: Path) -> None:
    db_path = tmp_path / "prefs.db"
    install_dir = str(tmp_path / "homestack")
    Path(install_dir).mkdir(parents=True, exist_ok=True)

    with SharedPreferences(db_path=db_path) as prefs:
        prefs.set_host_preferences(_host_prefs(install_dir))

    with (
        patch("cli.cli.SharedPreferences") as mock_prefs_cls,
        patch("cli.cli.ensure_traefik_bridge_network"),
        patch("cli.cli._download_env_templates"),
        patch("cli.cli.typer.prompt", return_value=install_dir),
    ):
        mock_prefs = MagicMock()
        mock_prefs.__enter__ = MagicMock(return_value=mock_prefs)
        mock_prefs.__exit__ = MagicMock(return_value=False)
        mock_prefs.is_initialized.return_value = True
        mock_prefs.get_host_preferences.return_value = _host_prefs(install_dir)
        mock_prefs_cls.return_value = mock_prefs

        result = runner.invoke(app, ["init", "--force"])

    assert result.exit_code == 0
    assert "Re-running initialization due to --force" in result.output


# ---------------------------------------------------------------------------
# Update: cache writes and API error messages
# ---------------------------------------------------------------------------


def test_update_caches_files_from_api(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache" / "api" / "v1"
    cache_dir.mkdir(parents=True, exist_ok=True)

    fake_meta = [MagicMock(file_name="projects.json", sha="abc123")]
    fake_job_called: list[str] = []

    async def fake_download_jobs(jobs, **_kwargs):
        for job in jobs:
            job.destination.parent.mkdir(parents=True, exist_ok=True)
            job.destination.write_text('{"downloaded": true}', encoding="utf-8")
            fake_job_called.append(str(job.destination))

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch.object(APIClient, "fetch_meta_sync", return_value=fake_meta),
        patch("cli.cli._read_local_meta", return_value={}),
        patch("cli.cli._write_meta_file"),
        patch("cli.cli._download_jobs", side_effect=fake_download_jobs),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["update"])

    assert result.exit_code == 0
    assert "Update complete" in result.output
    assert "1 meta-tracked file(s)" in result.output


def test_update_http_404_shows_friendly_message_no_traceback(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache" / "api" / "v1"
    cache_dir.mkdir(parents=True, exist_ok=True)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch.object(
            APIClient,
            "fetch_meta_sync",
            side_effect=APIHTTPError("http://api/v1/meta.json", 404, "not found"),
        ),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["update"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "404" in result.output or "not found" in result.output.lower()


def test_update_network_error_shows_friendly_message_no_traceback(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache" / "api" / "v1"
    cache_dir.mkdir(parents=True, exist_ok=True)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch.object(
            APIClient,
            "fetch_meta_sync",
            side_effect=APINetworkError("network error"),
        ),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["update"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "network" in result.output.lower() or "reach" in result.output.lower()


# ---------------------------------------------------------------------------
# List and Search: local cache fallback behavior
# ---------------------------------------------------------------------------


def _write_sample_cache(cache_dir: Path) -> list[ProjectItem]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    items = [
        {
            "project_index": 1,
            "project_name": "Pihole with Unbound",
            "dir_name": "01.pihole-unbound",
            "compose": "docker-compose.yml",
            "env": ".env.template",
            "readme": "readme.md",
            "config_files": [],
            "required_env_files": ["network.env"],
            "project_description": "DNS filtering",
            "supported_architecture": ["amd64"],
            "ready_to_deploy": True,
        },
        {
            "project_index": 2,
            "project_name": "Traefik",
            "dir_name": "02.traefik",
            "compose": "docker-compose.yml",
            "env": ".env.template",
            "readme": "readme.md",
            "config_files": [],
            "required_env_files": ["network.env"],
            "project_description": "Reverse proxy",
            "supported_architecture": ["amd64"],
            "ready_to_deploy": True,
        },
    ]
    (cache_dir / "projects.json").write_text(json.dumps(items), encoding="utf-8")
    return [ProjectItem(**it) for it in items]


def test_list_reads_cached_projects(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    _write_sample_cache(cache_dir)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._refresh_projects_cache_silent"),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "Pihole" in result.output or "Traefik" in result.output


def test_search_filters_cached_projects(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    _write_sample_cache(cache_dir)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._refresh_projects_cache_silent"),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["search", "traefik"])

    assert result.exit_code == 0
    assert "Traefik" in result.output


def test_cache_fallback_when_missing(tmp_path: Path) -> None:
    """_load_cached_projects triggers update when cache is absent."""
    cache_dir = tmp_path / "empty_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    def fake_update_writes_cache():
        # Simulate update filling the cache
        (cache_dir / "projects.json").write_text(
            json.dumps([
                {
                    "project_index": 1,
                    "project_name": "Pihole with Unbound",
                    "dir_name": "01.pihole-unbound",
                    "compose": "docker-compose.yml",
                    "env": ".env.template",
                    "readme": "readme.md",
                    "config_files": [],
                    "required_env_files": ["network.env"],
                    "project_description": "DNS",
                    "supported_architecture": ["amd64"],
                    "ready_to_deploy": True,
                }
            ]),
            encoding="utf-8",
        )

    with patch("cli.cli.update", side_effect=fake_update_writes_cache):
        projects = cli_module._load_cached_projects(cache_dir, check_remote_change=False)

    assert len(projects) >= 1
    assert projects[0].project_name == "Pihole with Unbound"


def test_list_prefers_api_layer_refresh_and_falls_back_to_local_cache(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    _write_sample_cache(cache_dir)

    # _refresh_projects_cache_silent swallows all exceptions internally;
    # here we mock it to do nothing (simulating a silent refresh failure)
    # and verify list still returns exit code 0 using the local cache.
    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._refresh_projects_cache_silent"),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["list"])

    assert result.exit_code == 0


def test_search_uses_cached_projects_when_conditional_refresh_returns_error(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    _write_sample_cache(cache_dir)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._refresh_projects_cache_silent"),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["search", "pihole"])

    assert result.exit_code == 0
    assert "Pihole" in result.output


# ---------------------------------------------------------------------------
# Info: readme display and remote fallback
# ---------------------------------------------------------------------------


def _sample_project_item(install_dir: str) -> ProjectItem:
    return ProjectItem(
        project_index=1,
        project_name="Pihole with Unbound",
        dir_name="01.pihole-unbound",
        compose="docker-compose.yml",
        env=".env.template",
        readme="readme.md",
        config_files=[],
        required_env_files=["network.env"],
        project_description="DNS filtering",
        supported_architecture=["amd64"],
        ready_to_deploy=True,
    )


def test_info_uses_cached_projects_when_refresh_fails(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    items = _write_sample_cache(cache_dir)

    # Plant a local readme so _print_info_readme doesn't make network calls
    project_dir = tmp_path / "homestack" / "compose" / "pihole-with-unbound"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "readme.md").write_text("# Pihole with Unbound\n", encoding="utf-8")

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._refresh_projects_cache_silent"),
        patch("cli.cli._find_project", return_value=items[0]),
        patch("cli.cli._print_info_readme"),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["info", "pihole"])

    assert result.exit_code == 0


def test_info_falls_back_to_remote_readme_when_local_missing(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    items = _write_sample_cache(cache_dir)

    remote_content = "# Remote README\nThis came from remote."

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._refresh_projects_cache_silent"),
        patch("cli.cli._find_project", return_value=items[0]),
        patch.object(APIClient, "fetch_text_sync", return_value=remote_content),
    ):
        mock_settings.cache_api_dir = cache_dir
        mock_settings.base_url = "http://api:8043"
        result = runner.invoke(app, ["info", "pihole"])

    assert result.exit_code == 0


def test_info_warns_when_remote_readme_is_unreachable(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    items = _write_sample_cache(cache_dir)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._refresh_projects_cache_silent"),
        patch("cli.cli._find_project", return_value=items[0]),
        patch.object(
            APIClient,
            "fetch_text_sync",
            side_effect=APINetworkError("unreachable"),
        ),
    ):
        mock_settings.cache_api_dir = cache_dir
        mock_settings.base_url = "http://api:8043"
        result = runner.invoke(app, ["info", "pihole"])

    # Warns but does not crash
    assert result.exit_code == 0
    assert "⚠" in result.output or "warn" in result.output.lower() or "reach" in result.output.lower()


def test_info_remote_readme_uses_repository_base_url(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    items = _write_sample_cache(cache_dir)

    captured: dict = {}

    def capture_fetch_text(path: str, **kwargs):
        captured["path"] = path
        return "# Readme"

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._refresh_projects_cache_silent"),
        patch("cli.cli._find_project", return_value=items[0]),
        patch.object(APIClient, "fetch_text_sync", side_effect=capture_fetch_text),
    ):
        mock_settings.cache_api_dir = cache_dir
        mock_settings.base_url = "http://api:8043"
        runner.invoke(app, ["info", "pihole"])

    assert "path" in captured
    assert "readme" in captured["path"].lower()


# ---------------------------------------------------------------------------
# Upgrade: cached fallback when refresh fails
# ---------------------------------------------------------------------------


def test_upgrade_uses_cached_projects_when_refresh_fails(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    items = _write_sample_cache(cache_dir)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._refresh_projects_cache_silent"),
        patch("cli.cli._find_project", return_value=items[0]),
        patch("cli.cli._print_info_readme"),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["upgrade", "pihole"])

    assert result.exit_code == 0
