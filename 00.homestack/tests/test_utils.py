"""Tests for shared utility helpers."""

import pytest
from utils.utils import ensure_directory_exists, write_file


def test_ensure_directory_exists_creates_missing_directories(tmp_path):
    """The helper should create nested directories when permissions allow it."""
    target_dir = tmp_path / "nested" / "output"

    ensure_directory_exists(target_dir)

    assert target_dir.exists()
    assert target_dir.is_dir()


def test_ensure_directory_exists_exits_with_clear_message_on_failure(tmp_path, capsys):
    """The helper should print a clear message and exit on creation failure."""
    blocked_path = tmp_path / "blocked"
    blocked_path.write_text("not a directory", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        ensure_directory_exists(blocked_path)

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert str(blocked_path) in captured.err
    assert "Create this directory yourself with the correct permissions" in captured.err


def test_write_file_creates_parent_directory(tmp_path):
    """write_file should create missing parent directories before writing."""
    output_file = tmp_path / "generated" / "output.txt"

    write_file(output_file, "hello")

    assert output_file.read_text(encoding="utf-8") == "hello"
