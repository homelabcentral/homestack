"""homestack CLI — orchestrator for self-hosted container deployments.

This module is the single entrypoint for all CLI commands. It defines
the Typer application and registers each sub-command. Business logic is
intentionally absent here; each command delegates to dedicated modules
under src/client/, src/api/, src/parsers/, and src/utils/.

Architecture overview:
    homestack (this module — orchestrator)
    ├── init     → reads host system info, prompts user for install directory,
    │              persists host preferences via SharedPreferences (src/utils/shared_pref.py),
    │              creates compose/ and data/ dirs, downloads shared env templates
    ├── update   → fetches remote meta.json via APIClient (src/api/client.py),
    │              compares SHA hashes against local cache, re-downloads stale JSON files
    ├── list     → reads local projects.json cache (or fetches remotely),
    │              renders table via Rich console
    ├── pull     → resolves project urls from projects.json,
    │              downloads docker-compose.yml + .env.template + readme.md +
    │              project config files via Downloader
    │              (src/client/downloader.py)
    ├── info     → displays project metadata and renders project README markdown
    │              (local copy when present, otherwise remote fallback)
    ├── deploy   → if local compose/.env already exist: start-equivalent flow;
    │              otherwise orchestrates: pull → parse .env.template → prompts
    │              (or use recommended) → write .env → preflight env-file checks
    │              → docker compose up -d
    ├── start    → validates local compose + env files and runs docker compose up -d
    ├── restart  → runs docker compose down then up -d for installed projects
    ├── stop     → removes project containers via docker compose down
    ├── remove   → docker compose down --rmi all + delete local project directory
    ├── search   → filters projects.json by name/description substring match
    └── upgrade  → displays project info for future upgrade workflow

Async boundary:
    Downloader (src/client/downloader.py) is fully async. Commands that invoke
    it wrap calls with asyncio.run() directly at each call site in cli.py.

Output strategy:
    All terminal output uses Rich (already a project dependency).
    - rich.console.Console for structured output (tables, panels, status)
    - typer.echo() only for simple one-liners or error paths
    Consistent colour roles: green = success, yellow = warning, red = error.

Error handling policy:
    Raise domain exceptions in business-logic modules; catch them here and
    convert to typer.Exit(1) with a Rich-formatted error message. Never let
    raw tracebacks reach the user in production mode.

Shell completion:
    Typer auto-registers completion commands (--install-completion,
    --show-completion) when shellingham is installed. No additional
    configuration is needed.
"""

from __future__ import annotations

import asyncio
import getpass
import grp
import json
import logging
import os
import platform
import re
import shutil
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import typer
from api.client import APIClient
from api.exceptions import (
    APIClientError,
    APIHTTPError,
    APINetworkError,
    APIParseError,
    APITimeoutError,
)
from client.downloader import (
    BatchDownloadError,
    Downloader,
    DownloaderError,
    DownloadHTTPError,
    DownloadJob,
)
from models.meta import MetaItem
from models.projects import ProjectItem
from models.readme_frontmatter import Step
from parsers import EnvTemplateParser
from rich.console import Console
from settings.settings import settings
from utils.app_logger import get_command_logger, setup_logging
from utils.compute_defaults import ComputeContext
from utils.docker_runtime import (
    DockerNetworkConflictError,
    DockerRuntimeError,
    deploy_project_stack,
    ensure_traefik_bridge_network,
    recreate_project_stack,
    remove_project_stack,
    restart_project_stack,
    start_project_stack,
    stop_project_stack,
    validate_compose_config,
)
from utils.markdown_printer import MarkdownPrinter
from utils.progress import DownloadProgressBar, OperationSpinner
from utils.project_table import ProjectTableBuilder
from utils.shared_pref import HostPreferences, SharedPreferences, SharedPrefsError
from utils.text_interpolation import (
    find_unresolved_placeholders,
    interpolate_text,
    load_interpolation_context,
)

from cli.questionary import (
    ask_confirm,
    ask_select,
    build_form_from_template,
    print_secrets_summary,
)

# ---------------------------------------------------------------------------
# Root application
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="homestack",
    help=(
        "Deploy self-hosted containers with ease — "
        "works similarly to Homebrew but for Docker Compose stacks."
    ),
    # Preserve the registration order in --help output.
    no_args_is_help=True,
    # Emit Rich-formatted error messages instead of raw Click errors.
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
)

setup_logging()
console = Console()


def _operation_spinner(message: str, *, verbose: bool, console: Console):
    if verbose:
        return nullcontext()
    return OperationSpinner(message, console=console)


def _require_init_or_exit() -> HostPreferences:
    try:
        with SharedPreferences() as prefs:
            if not prefs.is_initialized():
                typer.echo(
                    "homestack is not initialized. Run 'homestack init' first.",
                    err=True,
                )
                raise typer.Exit(code=1)
            return prefs.get_host_preferences()
    except SharedPrefsError as exc:
        typer.echo(f"Failed to load preferences: {exc}", err=True)
        raise typer.Exit(code=1)


def _friendly_api_error_message(exc: APIClientError, action: str) -> str:
    if isinstance(exc, APIHTTPError):
        if exc.status_code == 404:
            return (
                f"{action} failed: remote API file was not found (HTTP 404). "
                "Please verify the API source path and branch."
            )
        if exc.status_code in {401, 403}:
            return f"{action} failed: access to the remote API was denied (HTTP {exc.status_code})."
        if exc.status_code == 429:
            return f"{action} failed: rate limited by the remote API (HTTP 429). Please retry shortly."
        if 500 <= exc.status_code <= 599:
            return (
                f"{action} failed: remote API is currently unavailable "
                f"(HTTP {exc.status_code}). Please try again later."
            )
        return f"{action} failed: remote API returned HTTP {exc.status_code}."

    if isinstance(exc, APITimeoutError):
        return f"{action} failed: request timed out while contacting the remote API."
    if isinstance(exc, APINetworkError):
        return (
            f"{action} failed: could not reach the remote API. "
            "Check internet connectivity, DNS, or proxy settings."
        )
    if isinstance(exc, APIParseError):
        return (
            f"{action} failed: received an invalid response format from the remote API."
        )

    return f"{action} failed: remote API request did not complete successfully."


def _compose_dir_from_install_dir(install_dir: Path) -> Path:
    return install_dir / "compose"


def _data_dir_from_install_dir(install_dir: Path) -> Path:
    return install_dir / "data"


def _resolve_project_required_env_files(
    selected: ProjectItem, compose_dir: Path
) -> list[Path]:
    """Resolve required env files for a project to absolute paths.

    Front-matter values are treated as file names under <compose_dir>/00.env/
    unless an absolute path is provided. Projects must explicitly declare
    required_env_files in metadata; use an empty list to indicate that no
    shared env files are required.
    """
    required_env_files = selected.required_env_files
    if required_env_files is None:
        typer.echo(
            (
                f"Project '{selected.project_name}' does not define required_env_files "
                "in projects metadata. Update 00.api/v1/projects.json before "
                "running this command."
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    resolved: list[Path] = []

    for env_entry in required_env_files:
        env_path = Path(env_entry)
        if not env_path.is_absolute():
            env_path = compose_dir / "00.env" / env_path
        resolved.append(env_path.resolve())

    return resolved


def _validate_project_compose_config(
    compose_path: Path,
    project_slug: str,
    env_files: list[Path],
    *,
    show_output: bool = False,
) -> None:
    """Validate that the compose file parses with the full env-file set."""
    validate_compose_config(
        compose_path,
        project_slug,
        env_files,
        show_output=show_output,
    )


def _collect_ram_mb() -> int | None:
    page_size_name = "SC_PAGE_SIZE"
    pages_name = "SC_PHYS_PAGES"
    if not hasattr(os, "sysconf"):
        return None
    if page_size_name not in os.sysconf_names or pages_name not in os.sysconf_names:
        return None
    try:
        total_bytes = int(os.sysconf(page_size_name)) * int(os.sysconf(pages_name))
        return int(total_bytes / (1024 * 1024))
    except (ValueError, OSError):
        return None


def _collect_docker_gid() -> int | None:
    try:
        return int(grp.getgrnam("docker").gr_gid)
    except KeyError:
        return None


def _write_meta_file(cache_dir: Path, items: list[MetaItem]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = [item.__dict__ for item in items]
    (cache_dir / "meta.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def _read_local_meta(cache_dir: Path) -> dict[str, MetaItem]:
    meta_path = cache_dir / "meta.json"
    if not meta_path.exists():
        return {}
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    items = [MetaItem(**row) for row in payload]
    return {item.file_name: item for item in items}


_HOST_ENV_TEMPLATE_PAIRS = (
    ("host.env.template", "host.env"),
    ("network.env.template", "network.env"),
)


def _generate_env_files_from_templates(
    env_dir: Path,
    host_prefs: HostPreferences,
    logger: logging.Logger,
) -> None:
    """Generate host.env and network.env from their downloaded .template counterparts.

    Uses the same EnvTemplateParser → build_form_from_template pipeline as the
    deploy command. Failures are logged as warnings and skip that file — the user
    can re-generate manually later.
    """
    for template_name, output_name in _HOST_ENV_TEMPLATE_PAIRS:
        template_path = env_dir / template_name
        env_file = env_dir / output_name

        if not template_path.exists():
            logger.warning("Env template not found, skipping: %s", template_path)
            typer.echo(
                f"⚠ Template not found, skipping {output_name} generation",
                err=False,
            )
            continue

        try:
            parser = EnvTemplateParser(template_path)
            parsed = parser.parse()

            if parsed.warnings:
                for warning in parsed.warnings:
                    logger.warning(
                        "Template warning (%s): %s", template_name, warning.message
                    )

            generated = build_form_from_template(
                parsed,
                compute_context=ComputeContext(host_preferences=host_prefs),
            )
            env_file.write_text(generated.to_env_string())
            logger.info("Generated %s at %s", output_name, env_file)
            typer.echo(f"✓ Generated {output_name}")
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            logger.warning("Failed to generate %s: %s", output_name, exc)
            typer.echo(f"⚠ Could not generate {output_name}: {exc}", err=False)


def _download_env_templates(
    compose_dir: Path,
    logger: logging.Logger,
    *,
    console: Console | None = None,
) -> None:
    """Download all environment template files from 00.env/ to compose_dir/00.env/.

    Fetches the list of env templates from env.json and downloads them
    to the local installation directory. Failures are logged as warnings
    but do not block initialization — users can retry with 'homestack update'.
    """
    try:
        # Fetch the list of env template files from the remote API
        api_client = APIClient(environment="prod")
        env_items = api_client.fetch_env_sync()

        if not env_items:
            logger.warning("No environment templates found in remote API")
            return

        # Create the target directory for env files
        env_dir = compose_dir / "00.env"
        env_dir.mkdir(parents=True, exist_ok=True)

        # Build download jobs for all env files
        jobs: list[DownloadJob] = []
        for env_item in env_items:
            destination = env_dir / env_item.file_name
            jobs.append(
                DownloadJob(
                    url=f"{settings.base_url}/00.env/{env_item.file_name}",
                    destination=destination,
                )
            )

        # Execute downloads
        if jobs:
            with DownloadProgressBar(
                "Downloading environment templates",
                total=len(jobs),
                console=console,
            ) as bar:
                asyncio.run(_download_jobs(jobs, on_job_complete=bar.make_callback()))
            logger.info(
                "Downloaded %d environment template(s) to %s", len(jobs), env_dir
            )
            typer.echo(f"✓ Downloaded {len(jobs)} environment template(s)")

    except APIClientError as exc:
        # Log the error but don't block init — env files can be re-downloaded later
        error_msg = _friendly_api_error_message(
            exc, "Downloading environment templates"
        )
        logger.warning("Failed to download environment templates: %s", error_msg)
        typer.echo(f"⚠ {error_msg} (You can retry with 'homestack update')", err=False)
    except Exception as exc:
        # Catch any other unexpected errors (filesystem, etc.)
        logger.warning(
            "Unexpected error while downloading environment templates: %s", exc
        )
        typer.echo(
            f"⚠ Could not download environment templates: {exc} "
            "(You can retry with 'homestack update')",
            err=False,
        )


async def _download_jobs(
    jobs: list[DownloadJob],
    *,
    on_job_complete: Callable[[], None] | None = None,
) -> None:
    """Execute a batch of download jobs concurrently.

    When *on_job_complete* is provided each individual job is run through
    ``Downloader.download_file`` so the callback can fire as soon as each
    file finishes, allowing a progress bar to advance in real time.
    When *on_job_complete* is ``None`` the faster ``download_many`` path is
    used unchanged.
    """
    if not jobs:
        return

    if on_job_complete is None:
        async with Downloader() as downloader:
            await downloader.download_many(jobs, strict=True)
        return

    semaphore = asyncio.Semaphore(5)

    async def _run_one(
        job: DownloadJob, downloader: Downloader
    ) -> DownloadJob | DownloaderError:
        async with semaphore:
            try:
                await downloader.download_file(job.url, job.destination)
                return job
            except DownloaderError as exc:
                return exc
            finally:
                on_job_complete()

    async with Downloader() as downloader:
        outcomes = await asyncio.gather(*(_run_one(job, downloader) for job in jobs))

    failures = [
        (job, outcome)
        for job, outcome in zip(jobs, outcomes)
        if isinstance(outcome, DownloaderError)
    ]
    if failures:
        raise BatchDownloadError(failures)


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


def _refresh_projects_cache_silent(cache_dir: Path) -> None:
    try:
        api_client = APIClient(environment="prod")
        api_client.refresh_projects_cache_sync(cache_dir, silent=True)
    except Exception:
        # For list/search, remote errors must not surface; local cache is used.
        return


def _load_cached_projects(
    cache_dir: Path, check_remote_change: bool = False, filter_ready: bool = True
) -> list[ProjectItem]:
    projects_path = cache_dir / "projects.json"

    if check_remote_change:
        _refresh_projects_cache_silent(cache_dir)
    elif not projects_path.exists():
        update()

    projects_path = cache_dir / "projects.json"
    if not projects_path.exists():
        raise FileNotFoundError("projects.json is missing in local cache")

    payload = json.loads(projects_path.read_text(encoding="utf-8"))
    projects = [ProjectItem(**row) for row in payload]

    if filter_ready:
        projects = [p for p in projects if p.ready_to_deploy]

    return projects


def _find_project(project_name: str, projects: list[ProjectItem]) -> ProjectItem | None:
    normalized = _normalize_name(project_name)
    return next(
        (p for p in projects if _normalize_name(p.project_name) == normalized), None
    )


def _slug_project_name(project_name: str) -> str:
    """Return a filesystem-safe slug for a project_name.

    Lowercases the name and collapses any run of non-alphanumeric characters
    into a single hyphen, stripping leading/trailing hyphens.
    """
    slug = project_name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _filter_projects(query: str, projects: list[ProjectItem]) -> list[ProjectItem]:
    """Return projects whose searchable fields contain *query* (case-insensitive)."""
    q = query.strip().lower()
    matches: list[ProjectItem] = []
    for project in projects:
        description = project.project_description or project.description or ""
        architectures = " ".join(project.supported_architecture or [])
        website = project.project_website or ""
        source = project.project_source or ""
        haystack = (
            f"{project.project_name} {project.dir_name} {description} "
            f"{website} {source} {architectures}"
        ).lower()
        if q in haystack:
            matches.append(project)
    return sorted(matches, key=lambda p: p.project_index)


def _prompt_select_project(matches: list[ProjectItem]) -> ProjectItem:
    """Present a questionary select prompt and return the chosen project."""
    from questionary import Choice as QChoice

    choices = [
        QChoice(
            title=f"{p.project_name}  ({p.project_description or '-'})",
            value=p,
        )
        for p in matches
    ]
    return ask_select("Select a project:", choices)


def _select_project_from_query(
    project_name: str, projects: list[ProjectItem]
) -> ProjectItem:
    matches = _filter_projects(project_name, projects)

    if not matches:
        typer.echo(
            f"No projects found matching '{project_name}'. "
            "Run 'homestack list' to see all available projects.",
            err=True,
        )
        raise typer.Exit(code=1)

    console.print(
        ProjectTableBuilder.build(matches, title=f"Projects matching '{project_name}'")
    )

    if len(matches) == 1:
        return matches[0]
    return _prompt_select_project(matches)


def _resolve_project_config_destination(project_dir: Path, raw_path: str) -> Path:
    """Resolve and validate a config file destination inside *project_dir*."""
    normalized = raw_path.strip()
    if not normalized:
        raise ValueError("config_files path cannot be empty")

    candidate = Path(normalized)
    if candidate.is_absolute():
        raise ValueError(f"config_files path must be relative: {raw_path}")

    project_root = project_dir.resolve()
    destination = (project_dir / candidate).resolve()
    if destination == project_root or project_root not in destination.parents:
        raise ValueError(f"config_files path escapes project directory: {raw_path}")

    return destination


def _classify_optional_config_failures(
    error: BatchDownloadError,
    optional_config_jobs: dict[Path, str],
) -> tuple[list[tuple[DownloadJob, str]], list[tuple[DownloadJob, DownloaderError]]]:
    """Split missing optional config-file failures from all other download failures."""

    missing_optional_configs: list[tuple[DownloadJob, str]] = []
    remaining_failures: list[tuple[DownloadJob, DownloaderError]] = []

    for job, failure in error.failures:
        raw_path = optional_config_jobs.get(job.destination.resolve())
        if (
            raw_path is not None
            and isinstance(failure, DownloadHTTPError)
            and failure.status_code == 404
        ):
            missing_optional_configs.append((job, raw_path))
            continue
        remaining_failures.append((job, failure))

    return missing_optional_configs, remaining_failures


def _finalize_replacement_downloads(replacement_jobs: dict[Path, Path]) -> None:
    """Replace final destinations with successfully downloaded temporary files."""

    for temp_path, final_path in replacement_jobs.items():
        if temp_path.exists():
            os.replace(temp_path, final_path)


def _cleanup_replacement_downloads(replacement_jobs: dict[Path, Path]) -> None:
    """Remove temporary replacement files left behind after failed downloads."""

    for temp_path in replacement_jobs:
        if temp_path.exists():
            temp_path.unlink()


def _pull_project_files(
    selected: ProjectItem, compose_dir: Path, *, force: bool = False
) -> tuple[Path, int, list[Path]]:
    """Download project compose/env/readme/config files into compose directory.

    Returns:
        tuple of (project_dir, downloaded_count, existing_files_skipped)
    """
    project_dir = compose_dir / _slug_project_name(selected.project_name)
    project_dir.mkdir(parents=True, exist_ok=True)

    download_targets = [
        (selected.compose, project_dir / selected.compose),
        (selected.env, project_dir / selected.env),
        (selected.readme, project_dir / selected.readme),
    ]

    for config_file in selected.config_files or []:
        raw_path = getattr(config_file, "path", None)
        if raw_path is None and isinstance(config_file, dict):
            raw_path = config_file.get("path")
        if not isinstance(raw_path, str):
            typer.echo(
                (
                    f"Invalid config_files entry for project '{selected.project_name}': "
                    "missing string 'path'"
                ),
                err=True,
            )
            raise typer.Exit(code=1)
        try:
            destination = _resolve_project_config_destination(project_dir, raw_path)
        except ValueError as exc:
            typer.echo(
                f"Invalid config_files entry for project '{selected.project_name}': {exc}",
                err=True,
            )
            raise typer.Exit(code=1)
        download_targets.append((raw_path, destination))

    jobs: list[DownloadJob] = []
    skipped_existing_files: list[Path] = []
    optional_config_jobs: dict[Path, str] = {}
    replacement_jobs: dict[Path, Path] = {}
    for remote_name, destination in download_targets:
        destination.parent.mkdir(parents=True, exist_ok=True)

        is_optional_config = remote_name not in {
            selected.compose,
            selected.env,
            selected.readme,
        }

        if destination.exists() and not force:
            skipped_existing_files.append(destination)
            continue

        job_destination = destination
        if destination.exists() and force and is_optional_config:
            job_destination = destination.with_name(
                f".{destination.name}.incoming-{uuid4().hex}"
            )
            replacement_jobs[job_destination.resolve()] = destination
        elif destination.exists():
            destination.unlink()

        if is_optional_config:
            optional_config_jobs[job_destination.resolve()] = remote_name

        jobs.append(
            DownloadJob(
                url=f"{settings.base_url}/{selected.dir_name}/{remote_name}",
                destination=job_destination,
            )
        )

    if jobs:
        logger = get_command_logger("pull")
        downloaded_count = len(jobs)
        try:
            with DownloadProgressBar(
                "Pulling project files", total=len(jobs), console=console
            ) as bar:
                asyncio.run(_download_jobs(jobs, on_job_complete=bar.make_callback()))
        except BatchDownloadError as exc:
            missing_optional_configs, remaining_failures = (
                _classify_optional_config_failures(exc, optional_config_jobs)
            )
            if remaining_failures:
                _cleanup_replacement_downloads(replacement_jobs)
                raise BatchDownloadError(remaining_failures)

            downloaded_count -= len(missing_optional_configs)
            for job, raw_path in missing_optional_configs:
                warning = (
                    f"Optional config file does not exist remotely for "
                    f"'{selected.project_name}': {raw_path}"
                )
                logger.warning("%s (%s)", warning, job.url)
                typer.echo(f"⚠ {warning}")

        _finalize_replacement_downloads(replacement_jobs)
        return project_dir, downloaded_count, skipped_existing_files

    return project_dir, 0, skipped_existing_files


def _project_readme_name(project: ProjectItem) -> str:
    readme_name = project.readme.strip()
    return readme_name or "readme.md"


def _local_project_readme_path(project: ProjectItem, install_dir: Path) -> Path:
    compose_dir = _compose_dir_from_install_dir(install_dir)
    project_dir = compose_dir / _slug_project_name(project.project_name)
    return project_dir / _project_readme_name(project)


def _interpolate_project_text(
    text: str,
    project: ProjectItem,
    install_dir: Path,
    logger: logging.Logger,
    *,
    warning_collector: set[str] | None = None,
    emit_warnings: bool = True,
) -> str:
    """Interpolate text with project + shared env values in lenient mode."""
    compose_dir = _compose_dir_from_install_dir(install_dir)
    project_dir = compose_dir / _slug_project_name(project.project_name)
    shared_env_dir = compose_dir / "00.env"
    project_env_file = project_dir / ".env"

    context = load_interpolation_context(
        shared_env_dir=shared_env_dir,
        project_env_file=project_env_file,
        strict=False,
    )

    unresolved_in_context: list[str] = []
    for value in context.values():
        unresolved_in_context.extend(find_unresolved_placeholders(value))

    if unresolved_in_context:
        unique_context_tokens = sorted(set(unresolved_in_context))
        warning = (
            "Some env values contain unresolved placeholders; output will keep them "
            f"as-is: {', '.join(unique_context_tokens)}"
        )
        if warning_collector is not None:
            warning_collector.add(warning)
        if emit_warnings:
            logger.warning(warning)
            typer.echo(f"⚠ {warning}")

    rendered = interpolate_text(text, context, strict=False)
    unresolved_in_text = find_unresolved_placeholders(rendered)
    if unresolved_in_text:
        warning = (
            "Some placeholders in text could not be resolved and were left unchanged: "
            f"{', '.join(unresolved_in_text)}"
        )
        if warning_collector is not None:
            warning_collector.add(warning)
        if emit_warnings:
            logger.warning(warning)
            typer.echo(f"⚠ {warning}")

    return rendered


def _interpolate_project_metadata(
    project: ProjectItem,
    install_dir: Path,
    logger: logging.Logger,
    *,
    warning_collector: set[str] | None = None,
    emit_warnings: bool = True,
) -> ProjectItem:
    """Return a project copy with string metadata interpolated."""
    fields_to_render = {
        "description": project.description,
        "project_description": project.project_description,
        "project_website": project.project_website,
        "project_source": project.project_source,
        "project_docs": project.project_docs,
    }

    rendered_fields: dict[str, str | None] = {}
    for field_name, value in fields_to_render.items():
        if value:
            rendered_fields[field_name] = _interpolate_project_text(
                value,
                project,
                install_dir,
                logger,
                warning_collector=warning_collector,
                emit_warnings=emit_warnings,
            )
        else:
            rendered_fields[field_name] = value

    return replace(project, **rendered_fields)


def _print_project_access_hints(
    project: ProjectItem,
    install_dir: Path,
    logger: logging.Logger,
) -> None:
    """Display interpolated access URLs/docs after successful interactive commands."""
    rendered = _interpolate_project_metadata(project, install_dir, logger)
    website = (rendered.project_website or "").strip()
    docs = (rendered.project_docs or "").strip()

    if website:
        typer.echo(f"Access URL: {website}")
    if docs:
        typer.echo(f"Docs: {docs}")


def _print_info_readme(
    project: ProjectItem, install_dir: Path, logger: logging.Logger
) -> None:
    readme_title = f"README: {project.project_name}"
    readme_name = _project_readme_name(project)
    local_readme_path = _local_project_readme_path(project, install_dir)
    remote_readme_path = f"{project.dir_name}/{readme_name}"

    local_exists = local_readme_path.exists()
    if local_exists:
        try:
            local_text = local_readme_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            local_text = None

        if local_text is not None:
            rendered_local = _interpolate_project_text(
                local_text,
                project,
                install_dir,
                logger,
            )
            if MarkdownPrinter.print_markdown_text(
                console,
                rendered_local,
                title=readme_title,
            ):
                return

    if local_exists:
        warning = (
            f"Local README at {local_readme_path} could not be read; "
            "attempting remote README."
        )
    else:
        warning = (
            f"README not found locally at {local_readme_path}; "
            f"attempting remote README from {remote_readme_path}."
        )
    logger.warning(warning)
    typer.echo(f"⚠ {warning}")
    try:
        # README files live at the repository root project directories, not under
        # the static API path (00.api/v1).
        api_client = APIClient(environment="prod", base_url=settings.base_url)
        remote_readme = api_client.fetch_text_sync(remote_readme_path)
    except APIClientError as exc:
        if local_exists:
            warning = (
                f"Local README at {local_readme_path} could not be read, "
                "and remote README retrieval failed. README output is unavailable."
            )
        elif isinstance(exc, APIHTTPError) and exc.status_code == 404:
            warning = (
                f"README not found locally at {local_readme_path}, and remote README "
                f"was not found at {remote_readme_path}. Run 'homestack pull "
                f"{project.project_name}' or verify project metadata."
            )
        elif isinstance(exc, (APINetworkError, APITimeoutError)):
            warning = (
                f"README not found locally at {local_readme_path}, and remote README "
                "could not be reached. Check network connectivity and try again."
            )
        else:
            warning = (
                f"README not found locally at {local_readme_path}, and remote README "
                "retrieval failed. README output is unavailable."
            )

        logger.warning(
            "README display fallback failed for %s: %s", project.project_name, exc
        )
        typer.echo(f"⚠ {warning}")
        return

    rendered_remote = _interpolate_project_text(
        remote_readme,
        project,
        install_dir,
        logger,
    )

    if not MarkdownPrinter.print_markdown_text(
        console,
        rendered_remote,
        title=readme_title,
    ):
        warning = (
            f"README from remote path {remote_readme_path} is empty. "
            "README output is unavailable."
        )
        logger.warning(warning)
        typer.echo(f"⚠ {warning}")
        return

    if local_exists:
        warning = (
            f"Local README at {local_readme_path} could not be read; "
            "displaying remote README instead."
        )
    else:
        warning = (
            f"README not found locally at {local_readme_path}; "
            f"displaying remote README from {remote_readme_path}."
        )
    logger.warning(warning)
    typer.echo(f"⚠ {warning}")


def _confirm_pre_install_steps(
    project_name: str, steps: list[Step] | list[dict]
) -> None:
    """Require explicit yes/no confirmation for each pre-install step."""
    normalized_steps: list[tuple[int, str, str]] = []
    for index, step in enumerate(steps, start=1):
        if isinstance(step, dict):
            raw_number = step.get("number", index)
            description = str(step.get("description", "")).strip()
            todo = str(step.get("todo", "")).strip()
        else:
            raw_number = getattr(step, "number", index)
            description = str(getattr(step, "description", "")).strip()
            todo = str(getattr(step, "todo", "")).strip()

        try:
            number = int(raw_number)
        except (TypeError, ValueError):
            number = index

        normalized_steps.append((number, description, todo))

    normalized_steps.sort(key=lambda item: item[0])

    for number, description, todo in normalized_steps:
        title = description if description else "Complete pre-install task"
        completed = ask_confirm(
            f"Pre-install step {number}: {title}. Completed?",
            instruction=todo if todo else None,
            default=False,
        )

        if completed:
            continue

        typer.echo(
            f"Pre-install steps are required before deploying '{project_name}'.",
            err=True,
        )
        typer.echo(f"Step {number}: {title}", err=True)
        if todo:
            typer.echo(f"Description: {todo}", err=True)
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def init(
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-run initialization even if homestack is already initialized.",
    ),
) -> None:
    """Initialize homestack on this machine.

    Collects host system information (hostname, username, UID, GID, available
    CPU cores, RAM) and optionally prompts the user for install location and
    preferences. All values are persisted in a local sqlitedict database so
    downstream commands (deploy, pull, etc.) can reference them without
    asking again.
    """
    logger = get_command_logger("init")

    try:
        with SharedPreferences() as prefs:
            already_initialized = prefs.is_initialized()

            if already_initialized and not force:
                current = prefs.get_host_preferences()
                logger.info(
                    "Init skipped, already initialized with install_dir=%s",
                    current.install_dir,
                )
                typer.echo(
                    f"homestack is already initialized (install_dir={current.install_dir})."
                )
                return

            suggested_install_dir = str(Path.home() / "homestack")
            if already_initialized:
                current = prefs.get_host_preferences()
                if force:
                    logger.info(
                        "Force re-initialization requested for current install_dir=%s",
                        current.install_dir,
                    )
                    typer.echo("Re-running initialization due to --force.")
                suggested_install_dir = current.install_dir

            install_dir_text = typer.prompt(
                "Install directory", default=suggested_install_dir
            )
            install_dir = Path(install_dir_text).expanduser().resolve()
            compose_dir = _compose_dir_from_install_dir(install_dir)
            data_dir = _data_dir_from_install_dir(install_dir)
            install_dir.mkdir(parents=True, exist_ok=True)
            compose_dir.mkdir(parents=True, exist_ok=True)
            data_dir.mkdir(parents=True, exist_ok=True)

            # Ensure the path is writable before persisting it.
            test_file = install_dir / ".homestack-write-test"
            try:
                test_file.write_text("ok", encoding="utf-8")
                test_file.unlink(missing_ok=True)
            except OSError as exc:
                typer.echo(
                    f"Install directory is not writable: {install_dir} ({exc})",
                    err=True,
                )
                raise typer.Exit(code=1)

            disk_total_gb = round(shutil.disk_usage(install_dir).total / (1024**3), 2)

            ensure_traefik_bridge_network()

            host_prefs = HostPreferences(
                username=getpass.getuser(),
                uid=os.getuid() if hasattr(os, "getuid") else None,
                gid=os.getgid() if hasattr(os, "getgid") else None,
                docker_gid=_collect_docker_gid(),
                architecture=platform.machine() or "unknown",
                cpu_count=os.cpu_count() or 1,
                ram_mb=_collect_ram_mb(),
                install_dir=str(install_dir),
                install_dir_total_gb=disk_total_gb,
            )

            prefs.set_host_preferences(host_prefs)
            logger.info(
                "Initialization completed for install_dir=%s", host_prefs.install_dir
            )

            # Download environment template files from 00.env/
            typer.echo("Downloading environment templates...")
            _download_env_templates(compose_dir, logger, console=console)

            # Generate host.env and network.env from the downloaded templates
            typer.echo("Generating environment files...")
            _generate_env_files_from_templates(
                compose_dir / "00.env", host_prefs, logger
            )

            typer.echo("homestack initialization completed.")
            typer.echo(f"Install directory: {host_prefs.install_dir}")
            typer.echo(
                f"CPU cores: {host_prefs.cpu_count}, RAM: {host_prefs.ram_mb or 'unknown'} MB"
            )
    except SharedPrefsError as exc:
        logger.exception("Initialization failed")
        typer.echo(f"Failed to initialize preferences: {exc}", err=True)
        raise typer.Exit(code=1)
    except (DockerNetworkConflictError, DockerRuntimeError) as exc:
        logger.exception("Initialization failed while preparing Docker network")
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)


@app.command()
def update() -> None:
    """Check the remote API for updates and refresh the local cache.

    Fetches meta.json from the remote API via APIClient and compares the SHA hash
    of each tracked file against the locally cached version. Any file whose hash
    has changed (or that does not exist locally) is re-downloaded and written to
    the cache directory. The updated meta.json is then written to record the new
    hashes. Prints a summary of how many files were refreshed vs already current.
    """
    logger = get_command_logger("update")
    _require_init_or_exit()

    cache_dir = settings.cache_api_dir
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("Starting cache update")
        api_client = APIClient(environment="prod")
        remote_meta = api_client.fetch_meta_sync()
        local_meta = _read_local_meta(cache_dir)

        stale_files: list[str] = []
        for item in remote_meta:
            existing = local_meta.get(item.file_name)
            if existing is None or existing.sha != item.sha:
                stale_files.append(item.file_name)

        jobs: list[DownloadJob] = []
        for file_name in stale_files:
            destination = cache_dir / file_name
            if destination.exists():
                destination.unlink()
            jobs.append(
                DownloadJob(
                    url=f"{settings.api_url}/{file_name}",
                    destination=destination,
                )
            )

        if jobs:
            with DownloadProgressBar(
                "Refreshing cache",
                total=len(jobs),
                console=console,
            ) as bar:
                asyncio.run(_download_jobs(jobs, on_job_complete=bar.make_callback()))
        _write_meta_file(cache_dir, remote_meta)

        message = (
            f"Update complete. Refreshed {len(stale_files)} meta-tracked file(s), "
            f"{len(remote_meta) - len(stale_files)} already current."
        )
        logger.info(message)
        typer.echo(message)
    except typer.Exit:
        raise
    except APIClientError as exc:
        logger.error("Update failed due to API error: %s", exc)
        typer.echo(_friendly_api_error_message(exc, "Update"), err=True)
        raise typer.Exit(code=1)
    except Exception:
        logger.exception("Update failed")
        typer.echo(
            "Update failed: unexpected internal error. Check logs for details.",
            err=True,
        )
        raise typer.Exit(code=1)


@app.command(name="list")
def list_projects() -> None:
    """List all deployable projects.

    Triggers an API-layer conditional refresh for projects.json and then reads
    the local cache. Remote failures are ignored for this command so existing
    local cache data can still be displayed.
    """
    logger = get_command_logger("list")
    host_prefs = _require_init_or_exit()
    install_dir = Path(host_prefs.install_dir)

    cache_dir = settings.cache_api_dir
    try:
        projects = sorted(
            _load_cached_projects(cache_dir, check_remote_change=True),
            key=lambda p: p.project_index,
        )
        warnings: set[str] = set()
        rendered_projects = [
            _interpolate_project_metadata(
                project,
                install_dir,
                logger,
                warning_collector=warnings,
                emit_warnings=False,
            )
            for project in projects
        ]
        for warning in sorted(warnings):
            logger.warning(warning)
            typer.echo(f"⚠ {warning}")

        table = ProjectTableBuilder.build(rendered_projects, title="Deployable Projects")
        console.print(table)
        logger.info("Listed %d project(s)", len(rendered_projects))
    except Exception as exc:
        logger.exception("List command failed")
        typer.echo(f"List failed: {exc}", err=True)
        raise typer.Exit(code=1)


@app.command()
def pull(
    project_name: str = typer.Argument(
        ...,
        help="Name of the project to pull (e.g. 'pihole-unbound', 'traefik').",
        show_default=False,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite local project files if they already exist.",
    ),
) -> None:
    """Pull compose, env template, readme, and optional config files for a project.

    Performs a substring search against local projects.json and displays the
    matching set in a table. If multiple projects match the query the user is
    prompted to select one via an interactive list. A single match is used
    automatically. Files are downloaded and written into
    <install_dir>/compose/<slug(project_name)>/ where the directory name is derived from
    the human-readable project name, not the server-side directory.
    """
    logger = get_command_logger("pull")
    host_prefs = _require_init_or_exit()
    cache_dir = settings.cache_api_dir

    try:
        projects = _load_cached_projects(cache_dir)
        selected = _select_project_from_query(project_name, projects)

        install_dir = Path(host_prefs.install_dir)
        compose_dir = _compose_dir_from_install_dir(install_dir)
        project_dir, downloaded_count, skipped_existing_files = _pull_project_files(
            selected, compose_dir, force=force
        )

        if skipped_existing_files and downloaded_count == 0:
            typer.echo(
                f"Project files already exist at {project_dir}. "
                "Use '--force' to overwrite local files.",
                err=True,
            )
            raise typer.Exit(code=1)

        if skipped_existing_files:
            typer.echo(
                f"Skipped {len(skipped_existing_files)} existing file(s). "
                "Use '--force' to overwrite local files."
            )

        logger.info("Pulled project '%s' into %s", selected.project_name, project_dir)
        if downloaded_count:
            typer.echo(f"Project files downloaded to {project_dir}")
    except typer.Exit:
        raise
    except Exception as exc:
        logger.exception("Pull failed for %s", project_name)
        typer.echo(f"Pull failed: {exc}", err=True)
        raise typer.Exit(code=1)


@app.command()
def info(
    project_name: str = typer.Argument(
        ...,
        help="Name of the project to show information about.",
        show_default=False,
    ),
) -> None:
    """Display detailed information about a project.

    Triggers an API-layer conditional refresh for projects.json, resolves the
    requested project from local cache, and renders embedded metadata from the
    project entry.
    """
    logger = get_command_logger("info")
    host_prefs = _require_init_or_exit()

    cache_dir = settings.cache_api_dir
    try:
        projects = _load_cached_projects(cache_dir, check_remote_change=True)

        project = _find_project(project_name, projects)
        if project is None:
            typer.echo(f"Project '{project_name}' not found.", err=True)
            raise typer.Exit(code=1)

        rendered_project = _interpolate_project_metadata(
            project,
            Path(host_prefs.install_dir),
            logger,
        )
        console.print(ProjectTableBuilder.build_project_info(rendered_project))
        _print_info_readme(project, Path(host_prefs.install_dir), logger)
        _print_project_access_hints(project, Path(host_prefs.install_dir), logger)
        logger.info("Displayed info for %s", project.project_name)
    except typer.Exit:
        raise
    except Exception as exc:
        logger.exception("Info command failed for %s", project_name)
        typer.echo(f"Info failed: {exc}", err=True)
        raise typer.Exit(code=1)


@app.command()
def deploy(
    project_name: str = typer.Argument(
        ...,
        help="Name of the project to deploy.",
        show_default=False,
    ),
    use_recommended: bool = typer.Option(
        False,
        "--use-recommended",
        "--use-recommends",
        help=(
            "Auto-fill values for variables with recommended values; prompt "
            "for variables without recommendations (except immutable values)."
        ),
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help=(
            "Overwrite local project files and existing .env during deploy. "
            "Without this flag, existing files are preserved."
        ),
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show docker compose command output while the operation runs.",
    ),
) -> None:
    """Deploy a project end-to-end.

    Full deployment flow:
          1. Pull project files (docker-compose.yml, .env.template, readme.md, and
              optional config files) into
           <compose_dir>/<project-slug>/ if not already present.
        2. Parse the .env.template via EnvTemplateParser to extract typed variables.
        3. Build an interactive questionary form from the parsed variables, or if
            --use-recommended is set, auto-fill values for variables that define a
            recommended value and prompt for the rest (immutable values still use
            their template value).
        4. Write the answered key=value pairs to <compose_dir>/<project-slug>/.env.
        5. Preflight check: verify every env file listed in the project's
            required_env_files metadata exists under <compose_dir>/00.env/
            unless an absolute path is configured.
        6. Validate the compose file with docker compose using the complete
           env-file set.
        7. Create and start project containers through docker compose up -d.
        8. Print a deployed container status summary on success.
    """
    logger = get_command_logger("deploy")
    host_prefs = _require_init_or_exit()

    cache_dir = settings.cache_api_dir
    projects = _load_cached_projects(cache_dir, check_remote_change=True)
    selected = _select_project_from_query(project_name, projects)

    install_dir = Path(host_prefs.install_dir)
    compose_dir = _compose_dir_from_install_dir(install_dir)
    project_dir = compose_dir / _slug_project_name(selected.project_name)
    template_path = project_dir / selected.env
    compose_path = project_dir / selected.compose

    if force:
        typer.echo("--force enabled: refreshing local project files.")
        project_dir, _, _ = _pull_project_files(selected, compose_dir, force=True)
        template_path = project_dir / selected.env
        compose_path = project_dir / selected.compose
    elif (
        not project_dir.exists()
        or not template_path.exists()
        or not compose_path.exists()
    ):
        typer.echo(
            f"Local files missing for '{selected.project_name}', pulling project files first..."
        )
        project_dir, _, _ = _pull_project_files(selected, compose_dir, force=False)
        template_path = project_dir / selected.env
        compose_path = project_dir / selected.compose

    if not template_path.exists():
        typer.echo(f"No env template found at {template_path}", err=True)
        raise typer.Exit(code=1)

    if not compose_path.exists():
        typer.echo(f"No docker-compose.yml found at {compose_path}", err=True)
        raise typer.Exit(code=1)

    env_file = project_dir / ".env"
    compose_file = compose_path.resolve()
    required_env_files = _resolve_project_required_env_files(selected, compose_dir)

    if env_file.exists() and not force:
        generated_env_file = env_file.resolve()
        compose_env_files = [generated_env_file, *required_env_files]

        missing_env_files = [
            env_path for env_path in compose_env_files if not env_path.exists()
        ]
        if missing_env_files:
            for missing_env_file in missing_env_files:
                typer.echo(f"Required env file not found: {missing_env_file}", err=True)
            typer.echo(
                "Please set up required env files before running 'homestack deploy'.",
                err=True,
            )
            raise typer.Exit(code=1)

        logger.info(
            "Deploy found existing local files; using start-equivalent flow: compose=%s cwd=%s",
            compose_file,
            project_dir,
        )
        try:
            with _operation_spinner(
                f"Deploying {selected.project_name}\u2026",
                verbose=verbose,
                console=console,
            ):
                _validate_project_compose_config(
                    compose_file,
                    _slug_project_name(selected.project_name),
                    compose_env_files,
                    show_output=verbose,
                )
                start_project_stack(
                    compose_file,
                    _slug_project_name(selected.project_name),
                    compose_env_files,
                    show_output=verbose,
                )
        except DockerRuntimeError as exc:
            logger.error("Docker start-equivalent deploy failed: %s", exc)
            typer.echo("Docker deploy failed.", err=True)
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1)

        logger.info("Docker start-equivalent deploy completed successfully")
        typer.echo("Docker deployment completed successfully.")
        _print_info_readme(selected, install_dir, logger)
        _print_project_access_hints(selected, install_dir, logger)
        return

    if selected.pre_install_steps:
        _confirm_pre_install_steps(selected.project_name, selected.pre_install_steps)

    parser = EnvTemplateParser(template_path)
    parsed = parser.parse()

    if parsed.warnings:
        for warning in parsed.warnings:
            logger.warning("Template warning: %s", warning.message)
            typer.echo(f"[warn] {warning.message}", err=True)

    try:
        generated = build_form_from_template(
            parsed,
            use_recommended=use_recommended,
            compute_context=ComputeContext(host_preferences=host_prefs),
        )
    except KeyboardInterrupt:
        logger.info("Deploy aborted by user during interactive prompts")
        typer.echo("\nAborted. No .env file was written.", err=True)
        raise typer.Exit(code=1)
    except ValueError as exc:
        logger.error("Deploy failed while resolving template values: %s", exc)
        typer.echo(f"Invalid template compute configuration: {exc}", err=True)
        raise typer.Exit(code=1)
    env_file.write_text(generated.to_env_string())
    typer.echo(f".env written to {env_file}")
    logger.info("Generated env file at %s", env_file)

    print_secrets_summary(generated)

    generated_env_file = env_file.resolve()
    compose_env_files = [generated_env_file, *required_env_files]

    missing_env_files = [
        env_path for env_path in compose_env_files if not env_path.exists()
    ]
    if missing_env_files:
        for missing_env_file in missing_env_files:
            typer.echo(f"Required env file not found: {missing_env_file}", err=True)
        typer.echo(
            "Please set up required env files before running 'homestack deploy'.",
            err=True,
        )
        raise typer.Exit(code=1)

    logger.info(
        "Deploying project via docker compose up -d: compose=%s cwd=%s",
        compose_file,
        project_dir,
    )
    try:
        with _operation_spinner(
            f"Deploying {selected.project_name}\u2026",
            verbose=verbose,
            console=console,
        ):
            _validate_project_compose_config(
                compose_file,
                _slug_project_name(selected.project_name),
                compose_env_files,
                show_output=verbose,
            )
            deployment = deploy_project_stack(
                compose_file,
                _slug_project_name(selected.project_name),
                compose_env_files,
                show_output=verbose,
            )
    except DockerRuntimeError as exc:
        logger.error("Docker compose deploy failed: %s", exc)
        typer.echo("Docker deploy failed.", err=True)
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    logger.info("Docker compose deploy completed successfully")
    typer.echo("Docker deployment completed successfully.")

    if deployment.containers:
        console.print(ProjectTableBuilder.build_container_status(deployment.containers))

    _print_info_readme(selected, install_dir, logger)
    _print_project_access_hints(selected, install_dir, logger)


@app.command()
def start(
    project_name: str = typer.Argument(
        ...,
        help="Name of the deployed project to start.",
        show_default=False,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show docker compose command output while the operation runs.",
    ),
) -> None:
    """Start a locally installed project using docker compose up -d.

    Uses the same env-file set as deploy (project .env plus required shared env
    files), passing all env file paths as absolute paths.
    """
    logger = get_command_logger("start")
    host_prefs = _require_init_or_exit()

    cache_dir = settings.cache_api_dir
    projects = _load_cached_projects(cache_dir, filter_ready=False)
    install_dir = Path(host_prefs.install_dir)
    compose_dir = _compose_dir_from_install_dir(install_dir)
    installed_projects = [
        project
        for project in projects
        if (compose_dir / _slug_project_name(project.project_name)).exists()
    ]

    if not installed_projects:
        typer.echo(
            "No locally installed projects were found. Run 'homestack pull' or 'homestack deploy' first.",
            err=True,
        )
        raise typer.Exit(code=1)

    selected = _select_project_from_query(project_name, installed_projects)

    project_dir = compose_dir / _slug_project_name(selected.project_name)
    compose_path = project_dir / selected.compose
    env_path = project_dir / ".env"
    required_env_files = _resolve_project_required_env_files(selected, compose_dir)

    if not compose_path.exists():
        typer.echo(f"No docker-compose.yml found at {compose_path}", err=True)
        raise typer.Exit(code=1)

    if not env_path.exists():
        typer.echo(f"No .env found at {env_path}", err=True)
        raise typer.Exit(code=1)

    compose_file = compose_path.resolve()
    generated_env_file = env_path.resolve()
    compose_env_files = [generated_env_file, *required_env_files]

    missing_env_files = [
        env_file for env_file in compose_env_files if not env_file.exists()
    ]
    if missing_env_files:
        for missing_env_file in missing_env_files:
            typer.echo(f"Required env file not found: {missing_env_file}", err=True)
        raise typer.Exit(code=1)

    logger.info(
        "Starting project via docker compose: compose=%s cwd=%s",
        compose_file,
        project_dir,
    )
    try:
        with _operation_spinner(
            f"Starting {selected.project_name}\u2026",
            verbose=verbose,
            console=console,
        ):
            _validate_project_compose_config(
                compose_file,
                _slug_project_name(selected.project_name),
                compose_env_files,
                show_output=verbose,
            )
            start_project_stack(
                compose_file,
                _slug_project_name(selected.project_name),
                compose_env_files,
                show_output=verbose,
            )
    except DockerRuntimeError as exc:
        logger.error("Docker compose start failed: %s", exc)
        typer.echo("Docker start failed.", err=True)
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    logger.info("Docker compose start completed successfully")
    typer.echo("Docker start completed successfully.")
    _print_info_readme(selected, install_dir, logger)
    _print_project_access_hints(selected, install_dir, logger)


@app.command()
def recreate(
    project_name: str = typer.Argument(
        ...,
        help="Name of the deployed project to recreate.",
        show_default=False,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show docker compose command output while the operation runs.",
    ),
) -> None:
    """Recreate a locally installed project using docker compose up -d --force-recreate.

    Uses the same env-file set as deploy (project .env plus required shared env
    files), passing all env file paths as absolute paths.
    """
    logger = get_command_logger("recreate")
    host_prefs = _require_init_or_exit()

    cache_dir = settings.cache_api_dir
    projects = _load_cached_projects(cache_dir, filter_ready=False)
    install_dir = Path(host_prefs.install_dir)
    compose_dir = _compose_dir_from_install_dir(install_dir)
    installed_projects = [
        project
        for project in projects
        if (compose_dir / _slug_project_name(project.project_name)).exists()
    ]

    if not installed_projects:
        typer.echo(
            "No locally installed projects were found. Run 'homestack pull' or 'homestack deploy' first.",
            err=True,
        )
        raise typer.Exit(code=1)

    selected = _select_project_from_query(project_name, installed_projects)

    project_dir = compose_dir / _slug_project_name(selected.project_name)
    compose_path = project_dir / selected.compose
    env_path = project_dir / ".env"
    required_env_files = _resolve_project_required_env_files(selected, compose_dir)

    if not compose_path.exists():
        typer.echo(f"No docker-compose.yml found at {compose_path}", err=True)
        raise typer.Exit(code=1)

    if not env_path.exists():
        typer.echo(f"No .env found at {env_path}", err=True)
        raise typer.Exit(code=1)

    compose_file = compose_path.resolve()
    generated_env_file = env_path.resolve()
    compose_env_files = [generated_env_file, *required_env_files]

    missing_env_files = [
        env_file for env_file in compose_env_files if not env_file.exists()
    ]
    if missing_env_files:
        for missing_env_file in missing_env_files:
            typer.echo(f"Required env file not found: {missing_env_file}", err=True)
        raise typer.Exit(code=1)

    logger.info(
        "Recreating project via docker compose up -d --force-recreate: compose=%s cwd=%s",
        compose_file,
        project_dir,
    )
    try:
        with _operation_spinner(
            f"Recreating {selected.project_name}\u2026",
            verbose=verbose,
            console=console,
        ):
            _validate_project_compose_config(
                compose_file,
                _slug_project_name(selected.project_name),
                compose_env_files,
                show_output=verbose,
            )
            recreate_project_stack(
                compose_file,
                _slug_project_name(selected.project_name),
                compose_env_files,
                show_output=verbose,
            )
    except DockerRuntimeError as exc:
        logger.error("Docker compose recreate failed: %s", exc)
        typer.echo("Docker recreate failed.", err=True)
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    logger.info("Docker compose recreate completed successfully")
    typer.echo("Docker recreate completed successfully.")
    _print_info_readme(selected, install_dir, logger)
    _print_project_access_hints(selected, install_dir, logger)


@app.command()
def restart(
    project_name: str = typer.Argument(
        ...,
        help="Name of the deployed project to restart.",
        show_default=False,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show docker compose command output while the operation runs.",
    ),
) -> None:
    """Restart a locally installed project by running docker compose down then up -d.

    Uses the same env-file set as deploy (project .env plus required shared env
    files), passing all env file paths as absolute paths.
    """
    logger = get_command_logger("restart")
    host_prefs = _require_init_or_exit()

    cache_dir = settings.cache_api_dir
    projects = _load_cached_projects(cache_dir, filter_ready=False)
    install_dir = Path(host_prefs.install_dir)
    compose_dir = _compose_dir_from_install_dir(install_dir)
    installed_projects = [
        project
        for project in projects
        if (compose_dir / _slug_project_name(project.project_name)).exists()
    ]

    if not installed_projects:
        typer.echo(
            "No locally installed projects were found. Run 'homestack pull' or 'homestack deploy' first.",
            err=True,
        )
        raise typer.Exit(code=1)

    selected = _select_project_from_query(project_name, installed_projects)

    project_dir = compose_dir / _slug_project_name(selected.project_name)
    compose_path = project_dir / selected.compose
    env_path = project_dir / ".env"
    required_env_files = _resolve_project_required_env_files(selected, compose_dir)

    if not compose_path.exists():
        typer.echo(f"No docker-compose.yml found at {compose_path}", err=True)
        raise typer.Exit(code=1)

    if not env_path.exists():
        typer.echo(f"No .env found at {env_path}", err=True)
        raise typer.Exit(code=1)

    compose_file = compose_path.resolve()
    generated_env_file = env_path.resolve()
    compose_env_files = [generated_env_file, *required_env_files]

    missing_env_files = [
        env_file for env_file in compose_env_files if not env_file.exists()
    ]
    if missing_env_files:
        for missing_env_file in missing_env_files:
            typer.echo(f"Required env file not found: {missing_env_file}", err=True)
        raise typer.Exit(code=1)

    logger.info(
        "Restarting project via docker compose down then up -d: compose=%s cwd=%s",
        compose_file,
        project_dir,
    )
    try:
        with _operation_spinner(
            f"Restarting {selected.project_name}\u2026",
            verbose=verbose,
            console=console,
        ):
            _validate_project_compose_config(
                compose_file,
                _slug_project_name(selected.project_name),
                compose_env_files,
                show_output=verbose,
            )
            restart_project_stack(
                compose_file,
                _slug_project_name(selected.project_name),
                compose_env_files,
                show_output=verbose,
            )
    except DockerRuntimeError as exc:
        logger.error("Docker compose restart failed: %s", exc)
        typer.echo("Docker restart failed.", err=True)
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    logger.info("Docker compose restart completed successfully")
    typer.echo("Docker restart completed successfully.")
    _print_info_readme(selected, install_dir, logger)
    _print_project_access_hints(selected, install_dir, logger)


@app.command()
def stop(
    project_name: str = typer.Argument(
        ...,
        help="Name of the deployed project to stop.",
        show_default=False,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show docker compose command output while the operation runs.",
    ),
) -> None:
    """Stop a deployed project using docker compose down.

    Filters available projects to those that are installed locally under the
    configured install directory, presents matching choices, and then removes
    the project's compose-managed containers.
    """
    logger = get_command_logger("stop")
    host_prefs = _require_init_or_exit()

    cache_dir = settings.cache_api_dir
    projects = _load_cached_projects(cache_dir, filter_ready=False)
    install_dir = Path(host_prefs.install_dir)
    compose_dir = _compose_dir_from_install_dir(install_dir)
    installed_projects = [
        project
        for project in projects
        if (compose_dir / _slug_project_name(project.project_name)).exists()
    ]

    if not installed_projects:
        typer.echo(
            "No locally installed projects were found. Run 'homestack pull' or 'homestack deploy' first.",
            err=True,
        )
        raise typer.Exit(code=1)

    selected = _select_project_from_query(project_name, installed_projects)

    project_dir = compose_dir / _slug_project_name(selected.project_name)
    compose_path = project_dir / selected.compose
    env_path = project_dir / ".env"
    required_env_files = _resolve_project_required_env_files(selected, compose_dir)

    if not compose_path.exists():
        typer.echo(f"No docker-compose.yml found at {compose_path}", err=True)
        raise typer.Exit(code=1)

    if not env_path.exists():
        typer.echo(f"No .env found at {env_path}", err=True)
        raise typer.Exit(code=1)

    compose_file = compose_path.resolve()
    generated_env_file = env_path.resolve()
    compose_env_files = [generated_env_file, *required_env_files]

    missing_env_files = [
        env_path for env_path in compose_env_files if not env_path.exists()
    ]
    if missing_env_files:
        for missing_env_file in missing_env_files:
            typer.echo(f"Required env file not found: {missing_env_file}", err=True)
        raise typer.Exit(code=1)

    logger.info(
        "Stopping project via docker compose down: compose=%s cwd=%s",
        compose_file,
        project_dir,
    )
    try:
        with _operation_spinner(
            f"Stopping {selected.project_name}\u2026",
            verbose=verbose,
            console=console,
        ):
            _validate_project_compose_config(
                compose_file,
                _slug_project_name(selected.project_name),
                compose_env_files,
                show_output=verbose,
            )
            stop_project_stack(
                compose_file,
                _slug_project_name(selected.project_name),
                compose_env_files,
                show_output=verbose,
            )
    except DockerRuntimeError as exc:
        logger.error("Docker compose down failed: %s", exc)
        typer.echo("Docker stop failed.", err=True)
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    logger.info("Docker compose down completed successfully")
    typer.echo("Docker stop completed successfully.")


@app.command()
def remove(
    project_name: str = typer.Argument(
        ...,
        help="Name of the deployed project to remove.",
        show_default=False,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show docker compose command output while the operation runs.",
    ),
) -> None:
    """Remove a locally installed project.

    Always runs docker compose down --rmi all using the full env-file set, then
    removes the local project directory.
    """
    logger = get_command_logger("remove")
    host_prefs = _require_init_or_exit()

    cache_dir = settings.cache_api_dir
    projects = _load_cached_projects(cache_dir, filter_ready=False)
    install_dir = Path(host_prefs.install_dir)
    compose_dir = _compose_dir_from_install_dir(install_dir)
    installed_projects = [
        project
        for project in projects
        if (compose_dir / _slug_project_name(project.project_name)).exists()
    ]

    if not installed_projects:
        typer.echo(
            "No locally installed projects were found. Run 'homestack pull' or 'homestack deploy' first.",
            err=True,
        )
        raise typer.Exit(code=1)

    selected = _select_project_from_query(project_name, installed_projects)

    project_dir = compose_dir / _slug_project_name(selected.project_name)
    compose_path = project_dir / selected.compose
    env_path = project_dir / ".env"
    required_env_files = _resolve_project_required_env_files(selected, compose_dir)

    if not compose_path.exists():
        typer.echo(f"No docker-compose.yml found at {compose_path}", err=True)
        raise typer.Exit(code=1)

    if not env_path.exists():
        typer.echo(f"No .env found at {env_path}", err=True)
        raise typer.Exit(code=1)

    compose_file = compose_path.resolve()
    generated_env_file = env_path.resolve()
    compose_env_files = [generated_env_file, *required_env_files]

    missing_env_files = [
        env_file for env_file in compose_env_files if not env_file.exists()
    ]
    if missing_env_files:
        for missing_env_file in missing_env_files:
            typer.echo(f"Required env file not found: {missing_env_file}", err=True)
        raise typer.Exit(code=1)

    logger.info(
        "Removing project via docker compose down --rmi all: compose=%s cwd=%s",
        compose_file,
        project_dir,
    )
    try:
        with _operation_spinner(
            f"Removing {selected.project_name}\u2026",
            verbose=verbose,
            console=console,
        ):
            _validate_project_compose_config(
                compose_file,
                _slug_project_name(selected.project_name),
                compose_env_files,
                show_output=verbose,
            )
            remove_project_stack(
                compose_file,
                _slug_project_name(selected.project_name),
                compose_env_files,
                show_output=verbose,
            )
    except DockerRuntimeError as exc:
        logger.error("Docker compose remove failed: %s", exc)
        typer.echo("Docker remove failed.", err=True)
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    try:
        shutil.rmtree(project_dir)
    except OSError as exc:
        logger.error("Failed to delete project directory %s: %s", project_dir, exc)
        typer.echo(f"Failed to remove project directory {project_dir}: {exc}", err=True)
        raise typer.Exit(code=1)

    logger.info("Project removed successfully: %s", project_dir)
    typer.echo(f"Project removed successfully: {project_dir}")


@app.command()
def search(
    project_name: str = typer.Argument(
        ...,
        help="Project name or keyword to search for.",
        show_default=False,
    ),
) -> None:
    """Search for a project by name or keyword.

    Performs a case-insensitive substring match against project names and
    descriptions and metadata fields in local projects.json. The command first
    triggers an API-layer conditional refresh and then searches local cache.
    """
    logger = get_command_logger("search")
    host_prefs = _require_init_or_exit()
    install_dir = Path(host_prefs.install_dir)

    cache_dir = settings.cache_api_dir
    try:
        projects = _load_cached_projects(cache_dir, check_remote_change=True)
        warnings: set[str] = set()
        rendered_projects = [
            _interpolate_project_metadata(
                project,
                install_dir,
                logger,
                warning_collector=warnings,
                emit_warnings=False,
            )
            for project in projects
        ]
        for warning in sorted(warnings):
            logger.warning(warning)
            typer.echo(f"⚠ {warning}")

        matches = _filter_projects(project_name, rendered_projects)

        if not matches:
            typer.echo(f"No projects found matching '{project_name}'.")
            logger.info("No search matches for query: %s", project_name)
            return

        table = ProjectTableBuilder.build(
            matches, title=f"Search results for '{project_name}'"
        )
        console.print(table)
        logger.info(
            "Search matched %d project(s) for query '%s'", len(matches), project_name
        )
    except Exception as exc:
        logger.exception("Search command failed")
        typer.echo(f"Search failed: {exc}", err=True)
        raise typer.Exit(code=1)


@app.command()
def upgrade(
    project_name: str = typer.Argument(
        ...,
        help="Name of the deployed project whose Docker image should be updated.",
        show_default=False,
    ),
) -> None:
    """Upgrade a deployed project to the latest Docker image.

    Triggers an API-layer conditional refresh for projects.json, resolves the
    requested project from local cache, and renders project metadata needed for
    upgrade operations.
    """
    logger = get_command_logger("upgrade")
    host_prefs = _require_init_or_exit()

    cache_dir = settings.cache_api_dir
    try:
        projects = _load_cached_projects(cache_dir, check_remote_change=True)

        project = _find_project(project_name, projects)
        if project is None:
            typer.echo(f"Project '{project_name}' not found.", err=True)
            raise typer.Exit(code=1)

        rendered_project = _interpolate_project_metadata(
            project,
            Path(host_prefs.install_dir),
            logger,
        )
        console.print(ProjectTableBuilder.build_project_info(rendered_project))
        _print_info_readme(project, Path(host_prefs.install_dir), logger)
        _print_project_access_hints(project, Path(host_prefs.install_dir), logger)
        logger.info("Displayed info for %s", project.project_name)
    except typer.Exit:
        raise
    except Exception as exc:
        logger.exception("Upgrade command failed for %s", project_name)
        typer.echo(f"Upgrade failed: {exc}", err=True)
        raise typer.Exit(code=1)
