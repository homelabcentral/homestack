"""Shared model for env metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnvItem:
    file_name: str
    description: str
    required: bool
