"""CLI tests: real-API integration + monkeypatch coverage for pull/deploy/start/stop/remove."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from api.client import APIClient
from cli import cli as cli_module
from cli.cli import app
from client.downloader import BatchDownloadError, DownloadHTTPError
from models.generated_env import GeneratedEnv
from models.projects import ProjectItem
from parsers import EnvTemplateParser
from typer.testing import CliRunner
from utils.docker_runtime import DockerRuntimeError
from utils.shared_pref import HostPreferences

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers / fixtures
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


def _project_item(**overrides) -> ProjectItem:
    defaults = {
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
    }
    defaults.update(overrides)
    return ProjectItem(**defaults)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_local_project_items() -> list[ProjectItem]:
    projects_path = _repo_root() / "00.api" / "v1" / "projects.json"
    payload = json.loads(projects_path.read_text(encoding="utf-8"))
    return [ProjectItem(**project) for project in payload]


def _first_project() -> ProjectItem:
    client = APIClient(environment="prod")
    payload = client.fetch_json_sync("projects.json")
    return ProjectItem(**payload[0])


@pytest.mark.integration
@pytest.mark.parametrize("project", _load_local_project_items())
def test_pull_all_projects_cli_into_temp_dir_strict_files(
    tmp_path: Path, project: ProjectItem
) -> None:
    install_dir = tmp_path / "homestack"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    source_projects = _repo_root() / "00.api" / "v1" / "projects.json"
    (cache_dir / "projects.json").write_text(
        source_projects.read_text(encoding="utf-8"), encoding="utf-8"
    )

    with (
        patch(
            "cli.cli._require_init_or_exit",
            return_value=_host_prefs(str(install_dir)),
        ),
        patch.object(cli_module.settings, "cache_api_dir", cache_dir),
        patch("cli.cli._prompt_select_project", return_value=project),
    ):
        result = runner.invoke(app, ["pull", project.dir_name])

    assert result.exit_code == 0, (
        "pull failed for project "
        f"index={project.project_index} "
        f"name={project.project_name} "
        f"dir={project.dir_name}:\n{result.output}"
    )

    project_dir = (
        install_dir / "compose" / cli_module._slug_project_name(project.project_name)
    )
    assert project_dir.exists(), (
        "project directory missing for "
        f"index={project.project_index} "
        f"name={project.project_name} "
        f"dir={project.dir_name}"
    )

    required_files = [project.compose, project.env, project.readme]
    for relative_path in required_files:
        assert (project_dir / relative_path).exists(), (
            "required pulled file missing for "
            f"index={project.project_index} "
            f"name={project.project_name} "
            f"dir={project.dir_name} file={relative_path}"
        )

    for config_file in project.config_files or []:
        config_path = getattr(config_file, "path", None)
        if config_path is None and isinstance(config_file, dict):
            config_path = config_file.get("path")
        assert isinstance(config_path, str) and config_path, (
            "invalid config_files metadata for "
            f"index={project.project_index} "
            f"name={project.project_name} "
            f"dir={project.dir_name}"
        )
        assert (project_dir / config_path).exists(), (
            "config file missing after pull for "
            f"index={project.project_index} "
            f"name={project.project_name} "
            f"dir={project.dir_name} file={config_path}"
        )


def test_pull_downloads_project_files_to_temp_compose_dir(tmp_path: Path):
    selected = _first_project()
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir(parents=True, exist_ok=True)

    project_dir, downloaded_count, skipped_existing = cli_module._pull_project_files(
        selected,
        compose_dir,
        force=False,
    )

    assert downloaded_count >= 3
    assert skipped_existing == []
    assert (project_dir / selected.compose).exists()
    assert (project_dir / selected.env).exists()
    assert (project_dir / selected.readme).exists()


def test_parse_env_template_from_real_download(tmp_path: Path):
    selected = _first_project()
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir(parents=True, exist_ok=True)

    project_dir, _, _ = cli_module._pull_project_files(
        selected, compose_dir, force=False
    )

    parser = EnvTemplateParser(project_dir / selected.env)
    parsed = parser.parse()

    assert parsed is not None
    assert parsed.variables is not None


def test_pull_with_force_overwrites_local_files(tmp_path: Path):
    selected = _first_project()
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir(parents=True, exist_ok=True)

    project_dir, _, _ = cli_module._pull_project_files(
        selected, compose_dir, force=False
    )
    compose_path = project_dir / selected.compose
    compose_path.write_text("modified\n", encoding="utf-8")

    cli_module._pull_project_files(selected, compose_dir, force=True)
    reloaded = compose_path.read_text(encoding="utf-8")

    assert reloaded != "modified\n"


def test_required_env_files_resolve_to_compose_env_dir(tmp_path: Path):
    selected = _first_project()
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir(parents=True, exist_ok=True)

    resolved = cli_module._resolve_project_required_env_files(selected, compose_dir)

    assert resolved
    for path in resolved:
        assert str(path).startswith(str((compose_dir / "00.env").resolve()))


# ---------------------------------------------------------------------------
# Config path validation (pure logic, no mocks or network)
# ---------------------------------------------------------------------------


def test_resolve_project_config_destination_validates_paths(tmp_path: Path) -> None:
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()

    valid = cli_module._resolve_project_config_destination(
        project_dir, "config/settings.yml"
    )
    assert valid == (project_dir / "config" / "settings.yml").resolve()


def test_resolve_project_config_destination_rejects_absolute_path(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()

    with pytest.raises(ValueError, match="relative"):
        cli_module._resolve_project_config_destination(project_dir, "/etc/passwd")


def test_resolve_project_config_destination_rejects_path_traversal(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()

    with pytest.raises(ValueError, match="escapes"):
        cli_module._resolve_project_config_destination(
            project_dir, "../../../etc/shadow"
        )


def test_pull_warns_and_skips_missing_optional_config_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir(parents=True, exist_ok=True)
    project = _project_item(
        project_name="Traefik",
        dir_name="02.traefik",
        config_files=[{"path": "data/acme.json"}, {"path": "data/config.yml"}],
    )

    async def fake_jobs(jobs, **_kwargs):
        missing_job = next(job for job in jobs if job.url.endswith("data/acme.json"))
        for job in jobs:
            if job == missing_job:
                continue
            job.destination.parent.mkdir(parents=True, exist_ok=True)
            job.destination.write_text("downloaded", encoding="utf-8")
        raise BatchDownloadError(
            [
                (
                    missing_job,
                    DownloadHTTPError(
                        missing_job.url,
                        404,
                        f"Remote file not found (404): {missing_job.url}",
                    ),
                )
            ]
        )

    with patch("cli.cli._download_jobs", side_effect=fake_jobs):
        project_dir, downloaded_count, skipped_existing = (
            cli_module._pull_project_files(
                project,
                compose_dir,
                force=False,
            )
        )

    output = capsys.readouterr().out
    assert downloaded_count == 4
    assert skipped_existing == []
    assert "Optional config file does not exist remotely" in output
    assert "data/acme.json" in output
    assert not (project_dir / "data" / "acme.json").exists()
    assert (project_dir / "data" / "config.yml").exists()


def test_pull_force_preserves_existing_optional_config_when_remote_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir(parents=True, exist_ok=True)
    project = _project_item(
        project_name="Traefik",
        dir_name="02.traefik",
        config_files=[{"path": "data/config.yml"}],
    )
    project_dir = compose_dir / "traefik"
    project_dir.mkdir(parents=True, exist_ok=True)
    existing_config = project_dir / "data" / "config.yml"
    existing_config.parent.mkdir(parents=True, exist_ok=True)
    existing_config.write_text("keep-me", encoding="utf-8")

    async def fake_jobs(jobs, **_kwargs):
        missing_job = next(job for job in jobs if job.url.endswith("data/config.yml"))
        for job in jobs:
            if job == missing_job:
                continue
            job.destination.parent.mkdir(parents=True, exist_ok=True)
            job.destination.write_text("downloaded", encoding="utf-8")
        raise BatchDownloadError(
            [
                (
                    missing_job,
                    DownloadHTTPError(
                        missing_job.url,
                        404,
                        f"Remote file not found (404): {missing_job.url}",
                    ),
                )
            ]
        )

    with patch("cli.cli._download_jobs", side_effect=fake_jobs):
        project_dir, downloaded_count, skipped_existing = (
            cli_module._pull_project_files(
                project,
                compose_dir,
                force=True,
            )
        )

    output = capsys.readouterr().out
    assert downloaded_count == 3
    assert skipped_existing == []
    assert "does not exist remotely" in output
    assert project_dir == compose_dir / "traefik"
    assert existing_config.read_text(encoding="utf-8") == "keep-me"


def test_pull_still_fails_when_required_file_is_missing(tmp_path: Path) -> None:
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir(parents=True, exist_ok=True)
    project = _project_item(
        project_name="Traefik",
        dir_name="02.traefik",
        config_files=[{"path": "data/config.yml"}],
    )

    async def fake_jobs(jobs, **_kwargs):
        missing_job = next(job for job in jobs if job.url.endswith(project.compose))
        for job in jobs:
            if job == missing_job:
                continue
            job.destination.parent.mkdir(parents=True, exist_ok=True)
            job.destination.write_text("downloaded", encoding="utf-8")
        raise BatchDownloadError(
            [
                (
                    missing_job,
                    DownloadHTTPError(
                        missing_job.url,
                        404,
                        f"Remote file not found (404): {missing_job.url}",
                    ),
                )
            ]
        )

    with patch("cli.cli._download_jobs", side_effect=fake_jobs):
        with pytest.raises(BatchDownloadError):
            cli_module._pull_project_files(project, compose_dir, force=False)


# ---------------------------------------------------------------------------
# Pull CLI command: overwrite refusal without --force
# ---------------------------------------------------------------------------


def test_pull_refuses_to_overwrite_existing_files_without_force(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item()
    project_dir = tmp_path / "homestack" / "compose" / "pihole-with-unbound"
    project_dir.mkdir(parents=True, exist_ok=True)

    # Pre-stage all three files to simulate already-pulled state
    for fname in [project.compose, project.env, project.readme]:
        (project_dir / fname).write_text("existing", encoding="utf-8")

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["pull", "pihole"])

    assert result.exit_code == 1
    assert "--force" in result.output or "already exist" in result.output


# ---------------------------------------------------------------------------
# Config file download: skip/force semantics via monkeypatched _download_jobs
# ---------------------------------------------------------------------------


def _make_config_project(config_path: str = "config/settings.yml") -> ProjectItem:
    return _project_item(config_files=[{"path": config_path}])


def test_pull_downloads_config_files(tmp_path: Path) -> None:
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    project = _make_config_project()
    downloaded: list[str] = []

    async def fake_jobs(jobs, **_):
        for job in jobs:
            job.destination.parent.mkdir(parents=True, exist_ok=True)
            job.destination.write_text("downloaded", encoding="utf-8")
            downloaded.append(str(job.destination))

    with patch("cli.cli._download_jobs", side_effect=fake_jobs):
        project_dir, count, skipped = cli_module._pull_project_files(
            project, compose_dir, force=False
        )

    assert count >= 4  # compose + env + readme + config
    assert skipped == []


def test_pull_skips_existing_config_files_without_force(tmp_path: Path) -> None:
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    project = _make_config_project()

    async def fake_jobs(jobs, **_):
        for job in jobs:
            job.destination.parent.mkdir(parents=True, exist_ok=True)
            job.destination.write_text("downloaded", encoding="utf-8")

    with patch("cli.cli._download_jobs", side_effect=fake_jobs):
        cli_module._pull_project_files(project, compose_dir, force=False)
        _, count2, skipped2 = cli_module._pull_project_files(
            project, compose_dir, force=False
        )

    assert count2 == 0
    assert len(skipped2) >= 4


def test_pull_force_overwrites_existing_config_files(tmp_path: Path) -> None:
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    project = _make_config_project()
    call_count: list[int] = [0]

    async def fake_jobs(jobs, **_):
        call_count[0] += len(jobs)
        for job in jobs:
            job.destination.parent.mkdir(parents=True, exist_ok=True)
            job.destination.write_text("downloaded", encoding="utf-8")

    with patch("cli.cli._download_jobs", side_effect=fake_jobs):
        cli_module._pull_project_files(project, compose_dir, force=False)
        _, count2, skipped2 = cli_module._pull_project_files(
            project, compose_dir, force=True
        )

    assert count2 >= 4
    assert skipped2 == []


def test_pull_rejects_unsafe_config_path(tmp_path: Path) -> None:
    project_dir = tmp_path / "compose" / "pihole-with-unbound"
    project_dir.mkdir(parents=True)

    with pytest.raises(ValueError, match="escapes"):
        cli_module._resolve_project_config_destination(project_dir, "../../etc/passwd")


# ---------------------------------------------------------------------------
# Deploy: env generation, start-equivalent flow, runtime errors
# ---------------------------------------------------------------------------


def _stage_project_files(project_dir: Path, project: ProjectItem) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / project.compose).write_text(
        "version: '3'\nservices:\n  app:\n    image: test:latest\n",
        encoding="utf-8",
    )
    (project_dir / project.env).write_text(
        "# @var MY_VAR [required] A value\nMY_VAR=\n",
        encoding="utf-8",
    )
    (project_dir / project.readme).write_text("# Readme\n", encoding="utf-8")


def test_deploy_uses_start_equivalent_flow_when_env_exists(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    project_dir = tmp_path / "homestack" / "compose" / "pihole-with-unbound"
    _stage_project_files(project_dir, project)
    env_file = project_dir / ".env"
    env_file.write_text("MY_VAR=value\n", encoding="utf-8")

    start_called: list[bool] = [False]

    def fake_start(compose_file, slug, env_files, *, show_output=False):
        assert show_output is False
        start_called[0] = True

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.OperationSpinner") as mock_spinner,
        patch("cli.cli.validate_compose_config"),
        patch("cli.cli.start_project_stack", side_effect=fake_start),
        patch("cli.cli._print_info_readme"),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["deploy", "pihole"])

    assert result.exit_code == 0
    assert start_called[0]
    assert mock_spinner.call_count == 1


def test_deploy_fails_when_compose_config_is_invalid(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    project_dir = tmp_path / "homestack" / "compose" / "pihole-with-unbound"
    _stage_project_files(project_dir, project)
    (project_dir / ".env").write_text("MY_VAR=value\n", encoding="utf-8")

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch(
            "cli.cli.validate_compose_config",
            side_effect=DockerRuntimeError("invalid compose"),
        ),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["deploy", "pihole"])

    assert result.exit_code == 1
    assert "failed" in result.output.lower() or "Docker" in result.output


def test_deploy_fails_when_required_env_files_metadata_is_missing(
    tmp_path: Path,
) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=None)
    project_dir = tmp_path / "homestack" / "compose" / "pihole-with-unbound"
    _stage_project_files(project_dir, project)
    (project_dir / ".env").write_text("MY_VAR=value\n", encoding="utf-8")

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["deploy", "pihole"])

    assert result.exit_code == 1
    assert "required_env_files" in result.output or "metadata" in result.output.lower()


# ---------------------------------------------------------------------------
# Stop
# ---------------------------------------------------------------------------


def _install_project(compose_dir: Path, project: ProjectItem) -> Path:
    project_dir = compose_dir / "pihole-with-unbound"
    _stage_project_files(project_dir, project)
    (project_dir / ".env").write_text("MY_VAR=value\n", encoding="utf-8")
    return project_dir


def test_stop_runs_docker_runtime(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    _install_project(compose_dir, project)

    stop_called: list[bool] = [False]

    def fake_stop(compose_file, slug, env_files, *, show_output=False):
        assert show_output is False
        stop_called[0] = True

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.validate_compose_config"),
        patch("cli.cli.stop_project_stack", side_effect=fake_stop),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["stop", "pihole"])

    assert result.exit_code == 0
    assert stop_called[0]


def test_stop_fails_when_no_installed_projects(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    # Do NOT create the project directory — nothing is installed

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["stop", "pihole"])

    assert result.exit_code == 1
    assert (
        "No locally installed" in result.output or "not found" in result.output.lower()
    )


def test_stop_uses_project_required_env_files(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=["network.env"])
    compose_dir = tmp_path / "homestack" / "compose"
    _install_project(compose_dir, project)

    # Create required env file
    env_dir = compose_dir / "00.env"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / "network.env").write_text("NETWORK=test\n", encoding="utf-8")

    stop_called: list[bool] = [False]

    def fake_stop(compose_file, slug, env_files, *, show_output=False):
        assert show_output is False
        stop_called[0] = True
        assert any("network.env" in str(p) for p in env_files)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.validate_compose_config"),
        patch("cli.cli.stop_project_stack", side_effect=fake_stop),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["stop", "pihole"])

    assert result.exit_code == 0
    assert stop_called[0]


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------


def test_start_runs_docker_runtime(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    _install_project(compose_dir, project)

    start_called: list[bool] = [False]

    def fake_start(compose_file, slug, env_files, *, show_output=False):
        assert show_output is False
        start_called[0] = True

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.validate_compose_config"),
        patch("cli.cli.start_project_stack", side_effect=fake_start),
        patch("cli.cli._print_info_readme"),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["start", "pihole"])

    assert result.exit_code == 0
    assert start_called[0]


def test_start_fails_when_required_env_files_metadata_is_missing(
    tmp_path: Path,
) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=None)
    compose_dir = tmp_path / "homestack" / "compose"
    _install_project(compose_dir, project)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["start", "pihole"])

    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Recreate
# ---------------------------------------------------------------------------


def test_recreate_runs_docker_runtime(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    _install_project(compose_dir, project)

    recreate_called: list[bool] = [False]

    def fake_recreate(compose_file, slug, env_files, *, show_output=False):
        assert show_output is False
        recreate_called[0] = True

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.validate_compose_config"),
        patch("cli.cli.recreate_project_stack", side_effect=fake_recreate),
        patch("cli.cli._print_info_readme"),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["recreate", "pihole"])

    assert result.exit_code == 0
    assert recreate_called[0]


def test_recreate_uses_project_required_env_files(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=["network.env"])
    compose_dir = tmp_path / "homestack" / "compose"
    _install_project(compose_dir, project)

    env_dir = compose_dir / "00.env"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / "network.env").write_text("NETWORK=test\n", encoding="utf-8")

    recreate_called: list[bool] = [False]

    def fake_recreate(compose_file, slug, env_files, *, show_output=False):
        assert show_output is False
        recreate_called[0] = True
        assert any("network.env" in str(p) for p in env_files)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.validate_compose_config"),
        patch("cli.cli.recreate_project_stack", side_effect=fake_recreate),
        patch("cli.cli._print_info_readme"),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["recreate", "pihole"])

    assert result.exit_code == 0
    assert recreate_called[0]


def test_recreate_fails_when_no_installed_projects(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["recreate", "pihole"])

    assert result.exit_code == 1
    assert (
        "No locally installed" in result.output or "not found" in result.output.lower()
    )


# ---------------------------------------------------------------------------
# Restart
# ---------------------------------------------------------------------------


def test_restart_runs_docker_runtime(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    _install_project(compose_dir, project)

    restart_called: list[bool] = [False]

    def fake_restart(compose_file, slug, env_files, *, show_output=False):
        assert show_output is False
        restart_called[0] = True

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.validate_compose_config"),
        patch("cli.cli.restart_project_stack", side_effect=fake_restart),
        patch("cli.cli._print_info_readme"),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["restart", "pihole"])

    assert result.exit_code == 0
    assert restart_called[0]


def test_restart_uses_project_required_env_files(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=["network.env"])
    compose_dir = tmp_path / "homestack" / "compose"
    _install_project(compose_dir, project)

    env_dir = compose_dir / "00.env"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / "network.env").write_text("NETWORK=test\n", encoding="utf-8")

    restart_called: list[bool] = [False]

    def fake_restart(compose_file, slug, env_files, *, show_output=False):
        assert show_output is False
        restart_called[0] = True
        assert any("network.env" in str(p) for p in env_files)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.validate_compose_config"),
        patch("cli.cli.restart_project_stack", side_effect=fake_restart),
        patch("cli.cli._print_info_readme"),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["restart", "pihole"])

    assert result.exit_code == 0
    assert restart_called[0]


def test_restart_fails_when_no_installed_projects(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["restart", "pihole"])

    assert result.exit_code == 1
    assert (
        "No locally installed" in result.output or "not found" in result.output.lower()
    )


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------


def test_remove_runs_runtime_and_deletes_project_dir(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    project_dir = _install_project(compose_dir, project)

    remove_called: list[bool] = [False]

    def fake_remove(compose_file, slug, env_files, *, show_output=False):
        assert show_output is False
        remove_called[0] = True

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.validate_compose_config"),
        patch("cli.cli.remove_project_stack", side_effect=fake_remove),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["remove", "pihole"])

    assert result.exit_code == 0
    assert remove_called[0]
    assert not project_dir.exists()


def test_start_passes_show_output_when_verbose_enabled(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    _install_project(compose_dir, project)

    verbose_values: list[bool] = []

    def fake_start(compose_file, slug, env_files, *, show_output=False):
        _ = compose_file
        _ = slug
        _ = env_files
        verbose_values.append(show_output)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.OperationSpinner") as mock_spinner,
        patch("cli.cli.validate_compose_config"),
        patch("cli.cli.start_project_stack", side_effect=fake_start),
        patch("cli.cli._print_info_readme"),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["start", "pihole", "--verbose"])

    assert result.exit_code == 0
    assert verbose_values == [True]
    assert mock_spinner.call_count == 0


def test_restart_passes_show_output_when_verbose_enabled(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    _install_project(compose_dir, project)

    verbose_values: list[bool] = []

    def fake_restart(compose_file, slug, env_files, *, show_output=False):
        _ = compose_file
        _ = slug
        _ = env_files
        verbose_values.append(show_output)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.OperationSpinner") as mock_spinner,
        patch("cli.cli.validate_compose_config"),
        patch("cli.cli.restart_project_stack", side_effect=fake_restart),
        patch("cli.cli._print_info_readme"),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["restart", "pihole", "--verbose"])

    assert result.exit_code == 0
    assert verbose_values == [True]
    assert mock_spinner.call_count == 0


# ---------------------------------------------------------------------------
# Pull: command-level error paths
# ---------------------------------------------------------------------------


def test_pull_exits_with_error_when_download_fails_with_non_404(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item()

    async def fake_jobs(jobs, **_):
        raise BatchDownloadError(
            [(jobs[0], DownloadHTTPError(jobs[0].url, 503, "Service Unavailable"))]
        )

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli._download_jobs", side_effect=fake_jobs),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["pull", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "Pull failed" in result.output or "503" in result.output


# ---------------------------------------------------------------------------
# Deploy: error paths
# ---------------------------------------------------------------------------


def test_deploy_exits_when_env_template_is_missing_after_pull(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    project_dir = tmp_path / "homestack" / "compose" / "pihole-with-unbound"
    project_dir.mkdir(parents=True, exist_ok=True)
    # Stage compose but NOT the env template
    (project_dir / project.compose).write_text("version: '3'\n", encoding="utf-8")
    (project_dir / project.readme).write_text("# Readme\n", encoding="utf-8")

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli._pull_project_files", return_value=(project_dir, 2, [])),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["deploy", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "env template" in result.output.lower() or "No env template" in result.output


def test_deploy_docker_failure_on_new_deploy_path(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    project_dir = tmp_path / "homestack" / "compose" / "pihole-with-unbound"
    _stage_project_files(project_dir, project)
    # No .env so it takes new-deploy path

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch(
            "cli.cli.build_form_from_template",
            return_value=GeneratedEnv(values={"MY_VAR": "test"}),
        ),
        patch("cli.cli.print_secrets_summary"),
        patch("cli.cli._validate_project_compose_config"),
        patch(
            "cli.cli.deploy_project_stack",
            side_effect=DockerRuntimeError("container failed to start"),
        ),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["deploy", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "Docker deploy failed" in result.output or "failed" in result.output.lower()


def test_deploy_missing_required_shared_env_file(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=["network.env"])
    project_dir = tmp_path / "homestack" / "compose" / "pihole-with-unbound"
    _stage_project_files(project_dir, project)
    (project_dir / ".env").write_text("MY_VAR=value\n", encoding="utf-8")
    # network.env is NOT created under compose/00.env/

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.validate_compose_config"),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["deploy", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert (
        "Required env file not found" in result.output or "network.env" in result.output
    )


def test_deploy_aborts_when_form_is_interrupted(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    project_dir = tmp_path / "homestack" / "compose" / "pihole-with-unbound"
    _stage_project_files(project_dir, project)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.build_form_from_template", side_effect=KeyboardInterrupt),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["deploy", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "Aborted" in result.output


# ---------------------------------------------------------------------------
# Start: error paths
# ---------------------------------------------------------------------------


def test_start_fails_when_env_file_is_missing(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    project_dir = compose_dir / "pihole-with-unbound"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / project.compose).write_text("version: '3'\n", encoding="utf-8")
    # .env is intentionally absent

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["start", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "No .env found" in result.output


def test_start_fails_when_compose_file_is_missing(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    project_dir = compose_dir / "pihole-with-unbound"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / ".env").write_text("MY_VAR=value\n", encoding="utf-8")

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["start", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "No docker-compose.yml found" in result.output


def test_start_fails_on_docker_runtime_error(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    _install_project(compose_dir, project)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.validate_compose_config"),
        patch(
            "cli.cli.start_project_stack",
            side_effect=DockerRuntimeError("containers crashed"),
        ),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["start", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "Docker start failed" in result.output or "crashed" in result.output


def test_start_fails_when_required_shared_env_file_is_missing(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=["network.env"])
    compose_dir = tmp_path / "homestack" / "compose"
    _install_project(compose_dir, project)
    # network.env is NOT created

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["start", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert (
        "Required env file not found" in result.output or "network.env" in result.output
    )


# ---------------------------------------------------------------------------
# Stop: error paths
# ---------------------------------------------------------------------------


def test_restart_fails_on_docker_runtime_error(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    _install_project(compose_dir, project)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.validate_compose_config"),
        patch(
            "cli.cli.restart_project_stack",
            side_effect=DockerRuntimeError("docker daemon unreachable"),
        ),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["restart", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "Docker restart failed" in result.output or "unreachable" in result.output


def test_restart_fails_when_env_file_is_missing(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    project_dir = compose_dir / "pihole-with-unbound"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / project.compose).write_text("version: '3'\n", encoding="utf-8")
    # .env is intentionally absent

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["restart", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "No .env found" in result.output


def test_restart_fails_when_compose_file_is_missing(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    project_dir = compose_dir / "pihole-with-unbound"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / ".env").write_text("MY_VAR=value\n", encoding="utf-8")

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["restart", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "No docker-compose.yml found" in result.output


def test_restart_fails_when_required_shared_env_file_is_missing(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=["network.env"])
    compose_dir = tmp_path / "homestack" / "compose"
    _install_project(compose_dir, project)
    # network.env is NOT created

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["restart", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert (
        "Required env file not found" in result.output or "network.env" in result.output
    )


def test_stop_fails_on_docker_runtime_error(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    _install_project(compose_dir, project)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.validate_compose_config"),
        patch(
            "cli.cli.stop_project_stack",
            side_effect=DockerRuntimeError("docker daemon unreachable"),
        ),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["stop", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "Docker stop failed" in result.output or "unreachable" in result.output


def test_stop_fails_when_env_file_is_missing(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    project_dir = compose_dir / "pihole-with-unbound"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / project.compose).write_text("version: '3'\n", encoding="utf-8")
    # .env is intentionally absent

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["stop", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "No .env found" in result.output


def test_stop_fails_when_compose_file_is_missing(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    project_dir = compose_dir / "pihole-with-unbound"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / ".env").write_text("MY_VAR=value\n", encoding="utf-8")

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["stop", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "No docker-compose.yml found" in result.output


# ---------------------------------------------------------------------------
# Remove: error paths
# ---------------------------------------------------------------------------


def test_remove_fails_on_docker_runtime_error(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    project_dir = _install_project(compose_dir, project)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.validate_compose_config"),
        patch(
            "cli.cli.remove_project_stack",
            side_effect=DockerRuntimeError("image removal failed"),
        ),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["remove", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert (
        "Docker remove failed" in result.output
        or "image removal failed" in result.output
    )
    assert project_dir.exists()  # directory should NOT have been deleted


def test_remove_fails_when_directory_deletion_raises(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    _install_project(compose_dir, project)

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.validate_compose_config"),
        patch("cli.cli.remove_project_stack"),
        patch("cli.cli.shutil.rmtree", side_effect=OSError("permission denied")),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["remove", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert (
        "Failed to remove project directory" in result.output
        or "permission denied" in result.output
    )


def test_remove_fails_when_env_file_is_missing(tmp_path: Path) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=[])
    compose_dir = tmp_path / "homestack" / "compose"
    project_dir = compose_dir / "pihole-with-unbound"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / project.compose).write_text("version: '3'\n", encoding="utf-8")

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["remove", "pihole"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "No .env found" in result.output


def test_deploy_missing_required_shared_env_file_uses_explicit_mock_object(
    tmp_path: Path,
) -> None:
    install_dir = str(tmp_path / "homestack")
    project = _project_item(required_env_files=["network.env"])
    project_dir = tmp_path / "homestack" / "compose" / "pihole-with-unbound"
    _stage_project_files(project_dir, project)

    generated_env = MagicMock()
    generated_env.to_env_string.return_value = "MY_VAR=value\n"

    with (
        patch("cli.cli._require_init_or_exit", return_value=_host_prefs(install_dir)),
        patch("cli.cli.settings") as mock_settings,
        patch("cli.cli._load_cached_projects", return_value=[project]),
        patch("cli.cli._select_project_from_query", return_value=project),
        patch("cli.cli.build_form_from_template", return_value=generated_env),
        patch("cli.cli.print_secrets_summary"),
    ):
        mock_settings.cache_api_dir = tmp_path / "cache"
        result = runner.invoke(app, ["deploy", "pihole"])

    assert result.exit_code == 1
    assert "Required env file not found" in result.output
