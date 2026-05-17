"""CLI tests: real-API integration + monkeypatch coverage for non-API behavior."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

from api.client import APIClient
from api.exceptions import APIHTTPError, APINetworkError, APITimeoutError
from cli import cli as cli_module
from cli.cli import app
from models.projects import ProjectItem
from typer.testing import CliRunner
from utils.docker_runtime import DockerNetworkConflictError
from utils.shared_pref import HostPreferences, SharedPreferences, SharedPrefsIOError

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
    assert all(project.dir_name for project in projects)


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
        patch("cli.cli._generate_env_files_from_templates"),
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


def test_update_network_error_shows_friendly_message_no_traceback(
    tmp_path: Path,
) -> None:
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


def test_list_deduplicates_interpolation_warnings(tmp_path: Path) -> None:
    install_dir = tmp_path / "homestack"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    items = [
        {
            "project_index": 1,
            "project_name": "Project One",
            "dir_name": "01.project-one",
            "compose": "docker-compose.yml",
            "env": ".env.template",
            "readme": "readme.md",
            "config_files": [],
            "required_env_files": ["network.env"],
            "project_description": "Service at ${MISSING_HOST}",
            "supported_architecture": ["amd64"],
            "ready_to_deploy": True,
        },
        {
            "project_index": 2,
            "project_name": "Project Two",
            "dir_name": "02.project-two",
            "compose": "docker-compose.yml",
            "env": ".env.template",
            "readme": "readme.md",
            "config_files": [],
            "required_env_files": ["network.env"],
            "project_description": "Dashboard at ${MISSING_HOST}",
            "supported_architecture": ["amd64"],
            "ready_to_deploy": True,
        },
    ]
    (cache_dir / "projects.json").write_text(json.dumps(items), encoding="utf-8")

    with (
        patch(
            "cli.cli._require_init_or_exit",
            return_value=_host_prefs(str(install_dir)),
        ),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._refresh_projects_cache_silent"),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    warning_text = (
        "Some placeholders in text could not be resolved and were left unchanged"
    )
    assert result.output.count(warning_text) == 1


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
            json.dumps(
                [
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
                ]
            ),
            encoding="utf-8",
        )

    with patch("cli.cli.update", side_effect=fake_update_writes_cache):
        projects = cli_module._load_cached_projects(
            cache_dir, check_remote_change=False
        )

    assert len(projects) >= 1
    assert projects[0].project_name == "Pihole with Unbound"


def test_list_prefers_api_layer_refresh_and_falls_back_to_local_cache(
    tmp_path: Path,
) -> None:
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


def test_search_uses_cached_projects_when_conditional_refresh_returns_error(
    tmp_path: Path,
) -> None:
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
    assert (
        "⚠" in result.output
        or "warn" in result.output.lower()
        or "reach" in result.output.lower()
    )


def test_info_interpolates_project_metadata_with_env_context(tmp_path: Path) -> None:
    install_dir = tmp_path / "homestack"
    cache_dir = tmp_path / "cache"
    items = _write_sample_cache(cache_dir)

    # Add placeholder-based metadata for interpolation.
    project = replace(
        items[0],
        project_website="https://${APP_NAME}.${SUBDOMAIN}.${DOMAIN}",
        project_docs="https://${APP_NAME}.${SUBDOMAIN}.${DOMAIN}/docs",
    )

    # Prepare shared and project env context.
    shared_env_dir = install_dir / "compose" / "00.env"
    shared_env_dir.mkdir(parents=True, exist_ok=True)
    (shared_env_dir / "host.env").write_text(
        "SUBDOMAIN=lab\nDOMAIN=example.com\n",
        encoding="utf-8",
    )

    project_dir = install_dir / "compose" / "pihole-with-unbound"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / ".env").write_text("APP_NAME=pihole\n", encoding="utf-8")
    (project_dir / "readme.md").write_text("# Pihole\n", encoding="utf-8")

    with (
        patch(
            "cli.cli._require_init_or_exit", return_value=_host_prefs(str(install_dir))
        ),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._refresh_projects_cache_silent"),
        patch("cli.cli._find_project", return_value=project),
        patch("cli.cli._print_info_readme"),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["info", "pihole"])

    assert result.exit_code == 0
    assert "https://pihole.lab.example.com" in result.output


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


# ---------------------------------------------------------------------------
# Init: error paths
# ---------------------------------------------------------------------------


def _mock_prefs(is_initialized: bool, install_dir: str) -> MagicMock:
    mock_prefs = MagicMock()
    mock_prefs.__enter__ = MagicMock(return_value=mock_prefs)
    mock_prefs.__exit__ = MagicMock(return_value=False)
    mock_prefs.is_initialized.return_value = is_initialized
    mock_prefs.get_host_preferences.return_value = _host_prefs(install_dir)
    return mock_prefs


def test_init_fails_when_preferences_db_is_corrupt(tmp_path: Path) -> None:
    with patch("cli.cli.SharedPreferences") as mock_prefs_cls:
        mock_prefs = MagicMock()
        mock_prefs.__enter__ = MagicMock(side_effect=SharedPrefsIOError("disk full"))
        mock_prefs.__exit__ = MagicMock(return_value=False)
        mock_prefs_cls.return_value = mock_prefs
        result = runner.invoke(app, ["init"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert (
        "Failed to initialize preferences" in result.output
        or "disk full" in result.output
    )


def test_init_fails_when_install_dir_is_not_writable(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    Path(install_dir).mkdir(parents=True, exist_ok=True)

    with (
        patch("cli.cli.SharedPreferences") as mock_prefs_cls,
        patch("cli.cli.typer.prompt", return_value=install_dir),
        patch("cli.cli.ensure_traefik_bridge_network"),
        patch("pathlib.Path.write_text", side_effect=OSError("read-only fs")),
    ):
        mock_prefs_cls.return_value = _mock_prefs(
            is_initialized=False, install_dir=install_dir
        )
        result = runner.invoke(app, ["init"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "writable" in result.output or "write" in result.output.lower()


def test_init_fails_when_docker_network_setup_raises(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    Path(install_dir).mkdir(parents=True, exist_ok=True)

    with (
        patch("cli.cli.SharedPreferences") as mock_prefs_cls,
        patch("cli.cli.typer.prompt", return_value=install_dir),
        patch(
            "cli.cli.ensure_traefik_bridge_network",
            side_effect=DockerNetworkConflictError("subnet clash"),
        ),
    ):
        mock_prefs_cls.return_value = _mock_prefs(
            is_initialized=False, install_dir=install_dir
        )
        result = runner.invoke(app, ["init"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "subnet clash" in result.output or "docker" in result.output.lower()


# ---------------------------------------------------------------------------
# Update: error paths
# ---------------------------------------------------------------------------


def test_update_timeout_shows_friendly_message(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache" / "api" / "v1"
    cache_dir.mkdir(parents=True, exist_ok=True)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch.object(
            APIClient,
            "fetch_meta_sync",
            side_effect=APITimeoutError("connection timed out"),
        ),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["update"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "timed out" in result.output or "timeout" in result.output.lower()


def test_update_batch_download_failure_exits_with_error(tmp_path: Path) -> None:
    from client.downloader import BatchDownloadError, DownloadHTTPError, DownloadJob

    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache" / "api" / "v1"
    cache_dir.mkdir(parents=True, exist_ok=True)

    stale_job = DownloadJob(
        url="https://api.example.com/v1/projects.json",
        destination=cache_dir / "projects.json",
    )
    fake_meta = [MagicMock(file_name="projects.json", sha="new")]
    batch_error = BatchDownloadError(
        [(stale_job, DownloadHTTPError(stale_job.url, 503, "Service Unavailable"))]
    )

    async def fake_download_jobs(jobs, **_kwargs):
        raise batch_error

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch.object(APIClient, "fetch_meta_sync", return_value=fake_meta),
        patch("cli.cli._read_local_meta", return_value={}),
        patch("cli.cli._download_jobs", side_effect=fake_download_jobs),
    ):
        mock_settings.cache_api_dir = cache_dir
        mock_settings.api_url = "https://api.example.com/v1"
        result = runner.invoke(app, ["update"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "unexpected internal error" in result.output.lower()


# ---------------------------------------------------------------------------
# List: error paths
# ---------------------------------------------------------------------------


def test_list_exits_with_error_when_cache_load_fails(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch(
            "cli.cli._load_cached_projects", side_effect=RuntimeError("cache broken")
        ),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["list"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "List failed" in result.output or "cache broken" in result.output


# ---------------------------------------------------------------------------
# Search: error paths
# ---------------------------------------------------------------------------


def test_search_exits_with_error_when_cache_load_fails(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch(
            "cli.cli._load_cached_projects", side_effect=RuntimeError("cache broken")
        ),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["search", "traefik"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "Search failed" in result.output or "cache broken" in result.output


def test_search_returns_zero_when_no_matches(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    _write_sample_cache(cache_dir)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._refresh_projects_cache_silent"),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["search", "zzz-no-match"])

    assert result.exit_code == 0
    assert "No projects found" in result.output or "zzz-no-match" in result.output


# ---------------------------------------------------------------------------
# Info: error paths
# ---------------------------------------------------------------------------


def test_info_exits_with_error_when_project_not_found(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    _write_sample_cache(cache_dir)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._refresh_projects_cache_silent"),
        patch("cli.cli._find_project", return_value=None),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["info", "unknown-project"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "not found" in result.output.lower()


def test_info_exits_with_error_when_cache_load_fails(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch(
            "cli.cli._load_cached_projects",
            side_effect=RuntimeError("projects.json corrupt"),
        ),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["info", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "Info failed" in result.output or "corrupt" in result.output


def test_info_warns_on_http_404_readme(tmp_path: Path) -> None:
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
            side_effect=APIHTTPError("http://api/readme.md", 404, "Not Found"),
        ),
    ):
        mock_settings.cache_api_dir = cache_dir
        mock_settings.base_url = "http://api:8043"
        result = runner.invoke(app, ["info", "pihole"])

    assert result.exit_code == 0
    assert "Traceback" not in result.output
    assert (
        "⚠" in result.output
        or "not found" in result.output.lower()
        or "404" in result.output
    )


# ---------------------------------------------------------------------------
# Upgrade: error paths
# ---------------------------------------------------------------------------


def test_upgrade_exits_when_project_not_found(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    _write_sample_cache(cache_dir)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._refresh_projects_cache_silent"),
        patch("cli.cli._find_project", return_value=None),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["upgrade", "no-such-project"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "not found" in result.output.lower()


def test_upgrade_exits_on_unexpected_cache_error(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", side_effect=OSError("disk error")),
    ):
        mock_settings.cache_api_dir = cache_dir
        result = runner.invoke(app, ["upgrade", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "Upgrade failed" in result.output or "disk error" in result.output


# ---------------------------------------------------------------------------
# _generate_env_files_from_templates
# ---------------------------------------------------------------------------


def _write_minimal_template(path: Path, key: str = "MY_VAR") -> None:
    path.write_text(
        "# METADATA --- START\n"
        "# DO NOT CHANGE THE BELOW\n"
        "Description=Test\n"
        "Required=true\n"
        "# METADATA --- END\n"
        f"\n{key}= # type=string | prompt=Enter value\n",
        encoding="utf-8",
    )


def test_generate_env_files_from_templates_writes_both_env_files(
    tmp_path: Path,
) -> None:
    import logging

    env_dir = tmp_path / "00.env"
    env_dir.mkdir()
    _write_minimal_template(env_dir / "host.env.template", "USER_NAME")
    _write_minimal_template(env_dir / "network.env.template", "IP_PRIVATE")

    mock_generated = MagicMock()
    mock_generated.to_env_string.return_value = "USER_NAME=alice\n"

    with patch("cli.cli.build_form_from_template", return_value=mock_generated):
        cli_module._generate_env_files_from_templates(
            env_dir, _host_prefs(str(tmp_path)), logging.getLogger("test")
        )

    assert (env_dir / "host.env").exists()
    assert (env_dir / "host.env").read_text(encoding="utf-8") == "USER_NAME=alice\n"
    assert (env_dir / "network.env").exists()


def test_generate_env_files_from_templates_skips_missing_template(
    tmp_path: Path,
) -> None:
    import logging

    env_dir = tmp_path / "00.env"
    env_dir.mkdir()
    # Only network template is present; host template is absent
    _write_minimal_template(env_dir / "network.env.template", "IP_PRIVATE")

    mock_generated = MagicMock()
    mock_generated.to_env_string.return_value = "IP_PRIVATE=10.0.0.1\n"

    with patch("cli.cli.build_form_from_template", return_value=mock_generated):
        cli_module._generate_env_files_from_templates(
            env_dir, _host_prefs(str(tmp_path)), logging.getLogger("test")
        )

    assert not (env_dir / "host.env").exists()
    assert (env_dir / "network.env").exists()
    assert (env_dir / "network.env").read_text(
        encoding="utf-8"
    ) == "IP_PRIVATE=10.0.0.1\n"


def test_download_env_templates_falls_back_to_local_templates(tmp_path: Path) -> None:
    import logging

    compose_dir = tmp_path / "install" / "compose"
    local_root = tmp_path / "repo"
    local_env_dir = local_root / "00.env"
    local_env_dir.mkdir(parents=True, exist_ok=True)
    (local_env_dir / "host.env.template").write_text("HOST_NAME=\n", encoding="utf-8")
    (local_env_dir / "network.env.template").write_text(
        "IP_PRIVATE=\n", encoding="utf-8"
    )

    with (
        patch("cli.cli.APIClient") as mock_api_client_cls,
        patch("cli.cli.settings") as mock_settings,
    ):
        mock_api_client_cls.return_value.fetch_env_sync.side_effect = APINetworkError(
            "unreachable"
        )
        mock_settings.root_dir = local_root

        cli_module._download_env_templates(
            compose_dir, logging.getLogger("test-download-fallback")
        )

    target_env_dir = compose_dir / "00.env"
    assert (target_env_dir / "host.env.template").exists()
    assert (target_env_dir / "network.env.template").exists()
