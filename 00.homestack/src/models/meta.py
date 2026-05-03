"""Shared model for API file metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetaItem:
    file_name: str
    last_modified: str
    sha: str
    md5: str
