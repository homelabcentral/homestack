"""Generate projects metadata from numbered directories into 00.api/v1/projects.json."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    from settings.settings import root_dir
except ModuleNotFoundError:
    src_dir = Path(__file__).resolve().parents[1]
    if str(src_dir) not in sys.path:
        sys.path.append(str(src_dir))
    from settings.settings import root_dir

from models.projects import ProjectItem
from parsers.readme_parser import ParsingError, ReadmeFrontMatterParser
from utils.utils import ensure_directory_exists


class Projects:
    """Reads numbered project directories and creates projects.json metadata."""

    def __init__(self, workspace_root: Path | None = None) -> None:
        if workspace_root is None:
            workspace_root = root_dir
        else:
            workspace_root = Path(workspace_root)
        self.workspace_root = workspace_root
        self.output_file = self.workspace_root / "00.api" / "v1" / "projects.json"

    @staticmethod
    def _extract_project_metadata(dir_name: str) -> tuple[int, str] | None:
        """Extract project index and fallback name from directory name like '01.pihole-unbound'."""
        match = re.match(r"^(\d+)\.(.+)$", dir_name)
        if match:
            index = int(match.group(1))
            fallback_name = match.group(2)
            if index > 0:  # Exclude 00.* directories
                return index, fallback_name
        return None

    @staticmethod
    def _read_readme_front_matter(readme_path: Path) -> dict[str, object]:
        if not readme_path.exists():
            return {}

        try:
            parsed = ReadmeFrontMatterParser(readme_path).parse()
            return parsed.model_dump(exclude_none=True)
        except (ParsingError, FileNotFoundError):
            return {}

    def collect(self) -> list[ProjectItem]:
        items: list[ProjectItem] = []

        for dir_path in sorted(self.workspace_root.iterdir()):
            if not dir_path.is_dir():
                continue

            metadata = self._extract_project_metadata(dir_path.name)
            if metadata is None:
                continue

            project_index, fallback_name = metadata

            # Look for docker-compose.yml
            compose_file = dir_path / "docker-compose.yml"
            compose_name = "docker-compose.yml" if compose_file.exists() else ""

            # Look for .env.template
            env_template = dir_path / ".env.template"
            env_name = ".env.template" if env_template.exists() else ""

            # Look for readme.md
            readme_file = dir_path / "readme.md"
            readme_name = "readme.md" if readme_file.exists() else ""
            front_matter = self._read_readme_front_matter(readme_file)
            project_name = str(front_matter.get("project_name", fallback_name))
            description = str(front_matter.get("project_description", ""))

            items.append(
                ProjectItem(
                    project_index=project_index,
                    project_name=project_name,
                    dir_name=dir_path.name,
                    compose=compose_name,
                    env=env_name,
                    readme=readme_name,
                    description=description,
                    project_description=front_matter.get("project_description"),
                    author=front_matter.get("author"),
                    project_source=front_matter.get("project_source"),
                    project_website=front_matter.get("project_website"),
                    project_docs=front_matter.get("project_docs"),
                    project_status=front_matter.get("project_status"),
                    stable_images=front_matter.get("stable_images"),
                    stable_versions=front_matter.get("stable_versions"),
                    latest_images=front_matter.get("latest_images"),
                    latest_versions=front_matter.get("latest_versions"),
                    warning=front_matter.get("warning"),
                    date=front_matter.get("date"),
                    last_updated=front_matter.get("last_updated"),
                    required_env_files=front_matter.get("required_env_files"),
                    supported_architecture=front_matter.get("supported_architecture"),
                    ready_to_deploy=front_matter.get("ready_to_deploy"),
                    config_files=front_matter.get("config_files"),
                    pre_install_steps=front_matter.get("pre_install_steps"),
                    post_install_steps=front_matter.get("post_install_steps"),
                    post_setup_steps=front_matter.get("post_setup_steps"),
                )
            )

        return items

    def write_json(self) -> list[dict[str, object]]:
        payload = [item.__dict__ for item in self.collect()]
        ensure_directory_exists(self.output_file.parent)
        self.output_file.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        return payload


if __name__ == "__main__":
    Projects().write_json()
