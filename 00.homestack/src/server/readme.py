"""Utilities for scanning numbered project directories for README front matter."""

import sys
from pathlib import Path

try:
    from parsers import ReadmeFrontMatter, ReadmeFrontMatterParser
    from settings.settings import root_dir
except ModuleNotFoundError:
    src_dir = Path(__file__).resolve().parents[1]
    if str(src_dir) not in sys.path:
        sys.path.append(str(src_dir))
    from parsers import ReadmeFrontMatter, ReadmeFrontMatterParser
    from settings.settings import root_dir


class Readme:
    """Collect YAML front matter from numbered project README files.

    The collector inspects directories whose names match ``NN.name``, looks for
    ``readme.md`` in each one, parses only the YAML front matter block, and skips
    directories whose README is missing or cannot be parsed.

    Attributes:
        workspace_root: Root directory containing project folders.
    """

    def __init__(self, workspace_root: Path | str | None = None) -> None:
        """Initialize the readme metadata collector.

        Args:
            workspace_root: Root directory to scan. Defaults to the project workspace root.
        """
        self.workspace_root = Path(workspace_root) if workspace_root else root_dir

    def collect(self) -> list[ReadmeFrontMatter]:
        """Return parsed README front matter from numbered project directories.

        Only directories whose names match ``NN.name`` are inspected. Each matching
        directory contributes at most one ``readme.md`` result, and unreadable or
        invalid files are reported to stderr and skipped.

        Returns:
            list[ReadmeFrontMatter]: Parsed front matter for successfully read README files.
        """
        readmes: list[ReadmeFrontMatter] = []

        # Find all numbered directories (00.project, 01.project, etc.)
        project_dirs = sorted(
            [
                d
                for d in self.workspace_root.iterdir()
                if d.is_dir() and self._is_project_dir(d.name)
            ]
        )

        for project_dir in project_dirs:
            readme_path = project_dir / "readme.md"
            if not readme_path.exists():
                continue

            try:
                parser = ReadmeFrontMatterParser(readme_path)
                front_matter = parser.parse()
                readmes.append(front_matter)
            except Exception as e:
                print(f"Warning: Failed to parse {readme_path}: {e}", file=sys.stderr)
                continue

        return readmes

    @staticmethod
    def _is_project_dir(dir_name: str) -> bool:
        """Check if directory name matches the numbered project pattern.

        Args:
            dir_name: Directory name to check.

        Returns:
            bool: True if the name matches pattern XX.name, False otherwise.
        """
        parts = dir_name.split(".", 1)
        return len(parts) == 2 and parts[0].isdigit() and len(parts[0]) == 2


if __name__ == "__main__":
    readmes = Readme().collect()
    print(f"Collected metadata from {len(readmes)} readme file(s).")
