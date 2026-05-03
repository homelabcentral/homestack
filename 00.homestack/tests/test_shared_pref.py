"""Tests for shared preferences persistence."""

from __future__ import annotations

from pathlib import Path

from utils.shared_pref import HostPreferences, SharedPreferences


def test_shared_preferences_initialization_flag(tmp_path: Path):
    db_path = tmp_path / "prefs.db"

    with SharedPreferences(db_path=db_path) as prefs:
        assert prefs.is_initialized() is False

        prefs.set_host_preferences(
            HostPreferences(
                username="tester",
                uid=1000,
                gid=1000,
                docker_gid=999,
                architecture="x86_64",
                cpu_count=8,
                ram_mb=16384,
                install_dir=str(tmp_path / "install"),
                install_dir_total_gb=256.0,
            )
        )

        assert prefs.is_initialized() is True

    with SharedPreferences(db_path=db_path) as prefs_again:
        assert prefs_again.is_initialized() is True
        loaded = prefs_again.get_host_preferences()

    assert loaded.username == "tester"
    assert loaded.cpu_count == 8
    assert loaded.install_dir.endswith("install")


def test_shared_preferences_set_and_get_many(tmp_path: Path):
    db_path = tmp_path / "prefs.db"

    with SharedPreferences(db_path=db_path) as prefs:
        prefs.set_many({"a": 1, "b": "two"})
        assert prefs.get("a") == 1
        assert prefs.get("b") == "two"
        assert prefs.get("missing", "fallback") == "fallback"
