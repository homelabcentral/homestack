"""Pydantic output model for a generated `.env` file."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field


@dataclass
class GeneratedSecret:
    """Plaintext secret captured during env generation, for end-of-run display.

    Attributes:
        key: Environment variable name this secret belongs to.
        kind: The value kind (``password``, ``passphrase``, or ``bcrypthash``).
        plaintext: Plaintext value before hashing (or the passphrase itself).
        description: Human-readable description from the env template, if present.
    """

    key: str
    kind: str
    plaintext: str
    description: str | None = None


class GeneratedEnv(BaseModel):
    """Output model for a generated `.env` file.

    Attributes:
        values: Mapping of environment variable names to their final string values.
        generated_secrets: Plaintext secrets produced during generation that
            the user must save securely.  Not written to disk.
    """

    values: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variable key/value pairs for the .env file.",
    )
    generated_secrets: list[GeneratedSecret] = Field(
        default_factory=list,
        description="Plaintext secrets produced during generation (passwords, passphrases, etc.).",
    )

    def to_env_string(self) -> str:
        """Render key=value lines suitable for writing to a `.env` file."""
        return "\n".join(f"{k}={v}" for k, v in self.values.items()) + "\n"
