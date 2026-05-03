import sys
from pathlib import Path


def ensure_directory_exists(directory_path: Path) -> None:
    """Ensure a directory exists or exit with a clear error message."""
    try:
        directory_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(
            (
                f"Unable to create directory '{directory_path}'. "
                "Create this directory yourself with the correct permissions "
                "and run the command again."
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


def write_file(file_path: Path, content: str) -> None:
    """
    Write the given content to the specified file path.

    Args:
        file_path (Path): The path to the file where the content will be written.
        content (str): The content to write to the file.
    """
    ensure_directory_exists(file_path.parent)
    with open(file_path, "w") as file:
        file.write(content)
