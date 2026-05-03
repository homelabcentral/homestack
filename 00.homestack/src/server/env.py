"""Generate env metadata from 00.env templates into 00.api/v1/env.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from settings.settings import root_dir
except ModuleNotFoundError:
    src_dir = Path(__file__).resolve().parents[1]
    if str(src_dir) not in sys.path:
        sys.path.append(str(src_dir))
    from settings.settings import root_dir

from models.env import EnvItem
from utils.utils import ensure_directory_exists


class Env:
    """Reads env and env.template files and creates env.json metadata."""

    def __init__(self, workspace_root: Path | None = None) -> None:
        if workspace_root is None:
            workspace_root = root_dir
        self.workspace_root = workspace_root
        self.env_dir = self.workspace_root / "00.env"
        self.output_file = self.workspace_root / "00.api" / "v1" / "env.json"

    @staticmethod
    def _parse_required(value: str) -> bool:
        return value.strip().lower() in {"1", "true", "yes", "y"}

    def _read_metadata_from_template(self, template_path: Path) -> tuple[str, bool]:
        description = ""
        required = False
        in_metadata = False

        for raw_line in template_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()

            if line == "# METADATA --- START":
                in_metadata = True
                continue

            if line == "# METADATA --- END":
                break

            if not in_metadata or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip().lower()
            value = value.strip()

            if key == "description":
                description = value
            elif key == "required":
                required = self._parse_required(value)

        return description, required

    def collect(self) -> list[EnvItem]:
        items: list[EnvItem] = []

        for template_path in sorted(self.env_dir.glob("*.env.template")):
            description, required = self._read_metadata_from_template(template_path)

            items.append(
                EnvItem(
                    file_name=template_path.name,
                    description=description,
                    required=required,
                )
            )

        return items

    def write_json(self) -> list[dict[str, str | bool]]:
        payload = [item.__dict__ for item in self.collect()]
        ensure_directory_exists(self.output_file.parent)
        self.output_file.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        return payload


if __name__ == "__main__":
    Env().write_json()
