"""Synchronous entrypoint for generating API JSON artifacts in sequence."""

from __future__ import annotations

from pathlib import Path

from settings.settings import root_dir

from . import generate_env_template
from .env import Env
from .meta import Meta
from .projects import Projects


def generate_all(
    workspace_root: Path | str | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Generate env.json, projects.json, and meta.json in that strict order."""
    if workspace_root is None:
        workspace = root_dir
    else:
        workspace = Path(workspace_root)

    generate_env_template.create_template_files(str(workspace))
    env_payload = Env(workspace_root=workspace).write_json()
    projects_payload = Projects(workspace_root=workspace).write_json()
    meta_payload = Meta(workspace_root=workspace).write_json()

    return {
        "env": env_payload,
        "projects": projects_payload,
        "meta": meta_payload,
    }


def main() -> None:
    payload = generate_all()
    print(
        "Generated env.json, projects.json, and meta.json "
        f"(env={len(payload['env'])}, projects={len(payload['projects'])}, meta={len(payload['meta'])})"
    )


if __name__ == "__main__":
    main()
