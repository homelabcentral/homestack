"""Shared Rich table builder for project catalog output."""

from __future__ import annotations

from typing import Any

from models.generated_env import GeneratedSecret
from models.projects import ProjectItem
from rich import box
from rich.panel import Panel
from rich.table import Table

from utils.docker_runtime import ContainerStatus


class ProjectTableBuilder:
    """Builds consistently formatted tables for project-facing CLI commands."""

    @staticmethod
    def _architectures(value: list[str] | None) -> str:
        if not value:
            return "-"
        return ", ".join(value)

    @staticmethod
    def _description(project: ProjectItem) -> str:
        return project.project_description or project.description or "-"

    @staticmethod
    def _website(project: ProjectItem) -> str:
        return project.project_website or "-"

    @staticmethod
    def _source(project: ProjectItem) -> str:
        return project.project_source or "-"

    @staticmethod
    def _build_table_panel(
        *,
        title: str,
        columns: list[dict[str, Any]],
        rows: list[tuple[str, ...]],
        show_lines: bool = False,
    ) -> Panel:
        table = Table(show_lines=show_lines, box=box.SIMPLE_HEAD)
        for column in columns:
            table.add_column(**column)

        for row in rows:
            table.add_row(*row)

        return Panel(table, title=title)

    @classmethod
    def build(cls, projects: list[ProjectItem], title: str) -> Panel:
        rows = [
            (
                str(project.project_index),
                project.project_name,
                cls._architectures(project.supported_architecture),
                cls._description(project),
                cls._website(project),
                cls._source(project),
            )
            for project in projects
        ]
        return cls._build_table_panel(
            title=title,
            columns=[
                {"header": "#", "justify": "right", "style": "cyan"},
                {"header": "Project Name", "style": "green"},
                {"header": "Architectures", "style": "magenta"},
                {"header": "Description", "style": "white"},
                {"header": "Website", "style": "blue"},
                {"header": "Source Code", "style": "blue"},
            ],
            rows=rows,
        )

    @classmethod
    def build_project_info(cls, project: ProjectItem) -> Panel:
        rows = [
            ("Project", project.project_name),
            ("Directory", project.dir_name),
            ("Compose", project.compose),
            ("Env template", project.env),
            ("Readme", project.readme),
            ("Description", cls._description(project)),
            ("Source", cls._source(project)),
            ("Website", cls._website(project)),
            ("Docs", project.project_docs or "-"),
            ("Status", project.project_status or "-"),
            ("Ready to deploy", str(project.ready_to_deploy)),
        ]
        return cls._build_table_panel(
            title=f"Project Info: {project.project_name}",
            columns=[
                {"header": "Field", "style": "cyan"},
                {"header": "Value", "style": "green"},
            ],
            rows=rows,
        )

    @classmethod
    def build_secrets_summary(
        cls, secrets: list[GeneratedSecret], title: str = "Generated Secrets"
    ) -> Panel:
        rows = [
            (secret.key, secret.description or "-", secret.kind, secret.plaintext)
            for secret in secrets
        ]
        return cls._build_table_panel(
            title=title,
            columns=[
                {"header": "Variable", "style": "cyan", "no_wrap": True},
                {"header": "Description", "style": "white"},
                {"header": "Kind", "style": "magenta"},
                {"header": "Plaintext / Password", "style": "green"},
            ],
            rows=rows,
            show_lines=True,
        )

    @classmethod
    def build_container_status(
        cls, containers: list[ContainerStatus], title: str = "Deployed Containers"
    ) -> Panel:
        rows = [
            (
                container.service_name,
                container.container_name,
                container.status,
                container.image,
            )
            for container in containers
        ]
        return cls._build_table_panel(
            title=title,
            columns=[
                {"header": "Service", "style": "cyan"},
                {"header": "Container", "style": "green"},
                {"header": "Status", "style": "magenta"},
                {"header": "Image", "style": "white"},
            ],
            rows=rows,
        )
