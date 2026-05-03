"""Shared model for project metadata."""

from __future__ import annotations

from dataclasses import dataclass

from .readme_frontmatter import ConfigFile, Step


@dataclass(frozen=True)
class ProjectItem:
    project_index: int
    project_name: str
    dir_name: str
    compose: str
    env: str
    readme: str
    description: str = ""
    project_description: str | None = None
    author: str | None = None
    project_source: str | None = None
    project_website: str | None = None
    project_docs: str | None = None
    project_status: str | None = None
    stable_images: list[str] | None = None
    stable_versions: list[str] | None = None
    latest_images: list[str] | None = None
    latest_versions: list[str] | None = None
    warning: str | None = None
    date: str | None = None
    last_updated: str | None = None
    required_env_files: list[str] | None = None
    supported_architecture: list[str] | None = None
    ready_to_deploy: bool | None = None
    config_files: list[ConfigFile] | None = None
    pre_install_steps: list[Step] | None = None
    post_install_steps: list[Step] | None = None
    post_setup_steps: list[Step] | None = None
