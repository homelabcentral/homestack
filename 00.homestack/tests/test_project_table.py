"""Tests for shared project table builder."""

from models.generated_env import GeneratedSecret
from models.projects import ProjectItem
from rich.panel import Panel
from utils.project_table import ProjectTableBuilder


def test_build_table_has_expected_columns(
    real_project_items: list[ProjectItem],
) -> None:
    projects = [real_project_items[0]]

    panel = ProjectTableBuilder.build(projects, title="Deployable Projects")
    assert isinstance(panel, Panel)
    table = panel.renderable

    assert [column.header for column in table.columns] == [
        "#",
        "Project Name",
        "Architectures",
        "Description",
        "Website",
        "Source Code",
    ]


def test_build_table_uses_fallback_values(
    real_project_items: list[ProjectItem],
) -> None:
    source = real_project_items[1]
    projects = [
        ProjectItem(
            project_index=source.project_index,
            project_name=source.project_name,
            dir_name=source.dir_name,
            compose=source.compose,
            env=source.env,
            readme=source.readme,
        )
    ]

    panel = ProjectTableBuilder.build(projects, title="Deployable Projects")
    assert isinstance(panel, Panel)
    table = panel.renderable

    assert table.row_count == 1
    assert table.columns[2]._cells[0] == "-"
    assert table.columns[3]._cells[0] == "-"
    assert table.columns[4]._cells[0] == "-"
    assert table.columns[5]._cells[0] == "-"


def test_build_project_info_uses_shared_fallbacks(
    real_project_items: list[ProjectItem],
) -> None:
    source = real_project_items[6]
    project = ProjectItem(
        project_index=source.project_index,
        project_name=source.project_name,
        dir_name=source.dir_name,
        compose=source.compose,
        env=source.env,
        readme=source.readme,
    )

    panel = ProjectTableBuilder.build_project_info(project)
    assert isinstance(panel, Panel)
    assert panel.title == f"Project Info: {source.project_name}"

    table = panel.renderable
    assert [column.header for column in table.columns] == ["Field", "Value"]
    assert table.row_count == 11
    assert table.columns[0]._cells[5] == "Description"
    assert table.columns[0]._cells[6] == "Source"
    assert table.columns[0]._cells[7] == "Website"
    assert table.columns[1]._cells[5] == "-"
    assert table.columns[1]._cells[6] == "-"
    assert table.columns[1]._cells[7] == "-"


def test_build_secrets_summary_has_expected_columns() -> None:
    secrets = [
        GeneratedSecret(
            key="NEXTAUTH_SECRET",
            kind="base64urlsafe",
            plaintext="secret-value",
            description="Auth secret",
        )
    ]

    panel = ProjectTableBuilder.build_secrets_summary(secrets)
    assert isinstance(panel, Panel)
    assert panel.title == "Generated Secrets"

    table = panel.renderable
    assert [column.header for column in table.columns] == [
        "Variable",
        "Description",
        "Kind",
        "Plaintext / Password",
    ]
    assert table.row_count == 1
    assert table.columns[0]._cells[0] == "NEXTAUTH_SECRET"
    assert table.columns[1]._cells[0] == "Auth secret"
    assert table.columns[2]._cells[0] == "base64urlsafe"
    assert table.columns[3]._cells[0] == "secret-value"


def test_build_secrets_summary_uses_description_fallback() -> None:
    secrets = [GeneratedSecret(key="PW", kind="password", plaintext="p@ss")]

    panel = ProjectTableBuilder.build_secrets_summary(secrets)
    table = panel.renderable

    assert table.columns[1]._cells[0] == "-"
