"""Persistent shared preferences for homestack.

Preferences are stored in a platformdirs-based SQLite dictionary (via sqlitedict)
so the CLI can be used from any working directory after installation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from settings.settings import settings
from sqlitedict import SqliteDict


class SharedPrefsError(Exception):
    """Base exception for shared preferences failures."""


class SharedPrefsIOError(SharedPrefsError):
    """Raised when preferences storage cannot be opened or written."""


class SharedPrefsSchemaError(SharedPrefsError):
    """Raised when preferences are missing required schema fields."""


@dataclass(frozen=True)
class HostPreferences:
    """Typed view for host and installation preferences."""

    username: str
    uid: int | None
    gid: int | None
    docker_gid: int | None
    architecture: str
    cpu_count: int
    ram_mb: int | None
    install_dir: str
    install_dir_total_gb: float | None


class SharedPreferences:
    """Context-managed key/value preferences store backed by sqlitedict."""

    SCHEMA_VERSION = 1

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or settings.prefs_db_path
        self._db: SqliteDict | None = None

    def __enter__(self) -> SharedPreferences:
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def open(self) -> None:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = SqliteDict(str(self.db_path), autocommit=False)
            self._db.setdefault("__schema_version__", self.SCHEMA_VERSION)
            self._db.commit()
        except Exception as exc:
            raise SharedPrefsIOError(
                f"Unable to open preferences DB at {self.db_path}: {exc}"
            ) from exc

    def close(self) -> None:
        if self._db is None:
            return
        try:
            self._db.commit()
            self._db.close()
        except Exception as exc:
            raise SharedPrefsIOError(
                f"Unable to close preferences DB at {self.db_path}: {exc}"
            ) from exc
        finally:
            self._db = None

    def is_initialized(self) -> bool:
        return bool(self.get("init.completed", False))

    def get(self, key: str, default: Any = None) -> Any:
        db = self._require_open()
        return db.get(key, default)

    def set(self, key: str, value: Any) -> None:
        db = self._require_open()
        db[key] = value
        db["meta.updated_at"] = _utc_now()
        db.commit()

    def set_many(self, values: dict[str, Any]) -> None:
        db = self._require_open()
        for key, value in values.items():
            db[key] = value
        db["meta.updated_at"] = _utc_now()
        db.commit()

    def set_host_preferences(self, prefs: HostPreferences) -> None:
        self.set_many(
            {
                "host.username": prefs.username,
                "host.uid": prefs.uid,
                "host.gid": prefs.gid,
                "host.docker_gid": prefs.docker_gid,
                "host.architecture": prefs.architecture,
                "host.cpu_count": prefs.cpu_count,
                "host.ram_mb": prefs.ram_mb,
                "install.dir": prefs.install_dir,
                "install.dir_total_gb": prefs.install_dir_total_gb,
                "init.completed": True,
                "init.completed_at": _utc_now(),
                "meta.schema_version": self.SCHEMA_VERSION,
            }
        )

    def get_host_preferences(self) -> HostPreferences:
        required = [
            "host.username",
            "host.architecture",
            "host.cpu_count",
            "install.dir",
        ]
        missing = [key for key in required if self.get(key) is None]
        if missing:
            raise SharedPrefsSchemaError(
                f"Preferences are missing required fields: {', '.join(missing)}"
            )

        return HostPreferences(
            username=str(self.get("host.username")),
            uid=self.get("host.uid"),
            gid=self.get("host.gid"),
            docker_gid=self.get("host.docker_gid"),
            architecture=str(self.get("host.architecture")),
            cpu_count=int(self.get("host.cpu_count")),
            ram_mb=self.get("host.ram_mb"),
            install_dir=str(self.get("install.dir")),
            install_dir_total_gb=self.get("install.dir_total_gb"),
        )

    def _require_open(self) -> SqliteDict:
        if self._db is None:
            raise SharedPrefsIOError("Preferences DB is not open")
        return self._db


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
