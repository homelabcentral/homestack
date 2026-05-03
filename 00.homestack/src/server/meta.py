"""Generate meta.json with file metadata including hashes and timestamps."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    from settings.settings import root_dir
except ModuleNotFoundError:
    src_dir = Path(__file__).resolve().parents[1]
    if str(src_dir) not in sys.path:
        sys.path.append(str(src_dir))
    from settings.settings import root_dir

from models.meta import MetaItem
from utils.utils import ensure_directory_exists


class Meta:
    """Reads JSON files in 00.api/v1 and creates metadata with hashes and timestamps."""

    def __init__(self, workspace_root: Path | None = None) -> None:
        if workspace_root is None:
            workspace_root = root_dir
        self.workspace_root = workspace_root
        self.api_dir = self.workspace_root / "00.api" / "v1"
        self.output_file = self.api_dir / "meta.json"

    @staticmethod
    def _calculate_sha256(file_path: Path) -> str:
        """Calculate SHA256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    @staticmethod
    def _calculate_md5(file_path: Path) -> str:
        """Calculate MD5 hash of a file."""
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()

    @staticmethod
    def _get_last_modified(file_path: Path) -> str:
        """Get last modified datetime as ISO format string."""
        timestamp = file_path.stat().st_mtime
        dt = datetime.fromtimestamp(timestamp)
        return dt.isoformat(timespec="seconds")

    @staticmethod
    def _normalize_last_modified(value: str) -> str:
        try:
            return datetime.fromisoformat(value).isoformat(timespec="seconds")
        except ValueError:
            return value

    def _load_existing_metadata(self) -> dict[str, MetaItem]:
        if not self.output_file.exists():
            return {}

        try:
            data = json.loads(self.output_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

        items: dict[str, MetaItem] = {}
        for raw_item in data:
            if not isinstance(raw_item, dict):
                continue

            file_name = raw_item.get("file_name")
            last_modified = raw_item.get("last_modified")
            sha = raw_item.get("sha")
            md5 = raw_item.get("md5")

            if not all(
                isinstance(value, str) for value in (file_name, last_modified, sha, md5)
            ):
                continue

            items[file_name] = MetaItem(
                file_name=file_name,
                last_modified=self._normalize_last_modified(last_modified),
                sha=sha,
                md5=md5,
            )

        return items

    def collect(self) -> list[MetaItem]:
        items: list[MetaItem] = []
        existing_items = self._load_existing_metadata()

        # Scan for all .json files except meta.json
        for json_file in sorted(self.api_dir.glob("*.json")):
            if json_file.name in {"meta.json", "readmes.json"}:
                continue

            sha = self._calculate_sha256(json_file)
            md5 = self._calculate_md5(json_file)
            existing_item = existing_items.get(json_file.name)
            if existing_item and existing_item.sha == sha and existing_item.md5 == md5:
                last_modified = existing_item.last_modified
            else:
                last_modified = self._get_last_modified(json_file)

            items.append(
                MetaItem(
                    file_name=json_file.name,
                    last_modified=last_modified,
                    sha=sha,
                    md5=md5,
                )
            )

        return items

    def write_json(self) -> list[dict[str, str]]:
        payload = [item.__dict__ for item in self.collect()]
        rendered = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"

        if (
            self.output_file.exists()
            and self.output_file.read_text(encoding="utf-8") == rendered
        ):
            return payload

        ensure_directory_exists(self.output_file.parent)
        self.output_file.write_text(rendered, encoding="utf-8")
        return payload


if __name__ == "__main__":
    Meta().write_json()
