"""Pydantic models for `.env.template` parsing and validation."""

from __future__ import annotations

import ipaddress
import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_MEMORY_PATTERN = re.compile(r"^[0-9]+[KMGT]$")


class EnvValueKind(str, Enum):
    """Supported variable kinds declared by `type=` metadata."""

    STRING = "string"
    PATH = "path"
    BOOLEAN = "boolean"
    INT = "int"
    FLOAT = "float"
    PASSWORD = "password"
    PASSPHRASE = "passphrase"
    BASE64 = "base64"
    BASE64URLSAFE = "base64urlsafe"
    BCRYPTHASH = "bcrypthash"
    MEMORY = "memory"
    IP = "ip"
    PORT = "port"


class EnvTemplateWarning(BaseModel):
    """Non-fatal parser warning tied to a line/field fragment."""

    line: int | None = Field(
        None, description="1-based line number where warning happened"
    )
    field: str | None = Field(None, description="Associated field name, if available")
    message: str = Field(..., description="Human-readable warning message")
    raw_fragment: str | None = Field(
        None, description="Raw fragment that caused the warning"
    )


class EnvTemplateMetadata(BaseModel):
    """Metadata extracted from `# METADATA --- START/END` block."""

    description: str | None = Field(
        None, description="Human-readable template description"
    )
    required: bool | None = Field(None, description="Whether this env file is required")
    extra: dict[str, str] = Field(
        default_factory=dict,
        description="Additional metadata entries not represented by explicit fields",
    )


class EnvTemplateChoice(BaseModel):
    """Questionary choice metadata for a variable."""

    value: str = Field(..., description="Choice value")
    description: str | None = Field(None, description="Optional choice description")
    default: bool | None = Field(None, description="Whether this choice is the default")


class EnvTemplateValueType(BaseModel):
    """Structured representation of `type=` metadata.

    For kinds supporting bounds (`string`, `int`, `float`, `password`, `passphrase`,
    `base64`, `base64urlsafe`),
    either bound may be omitted. If one argument is supplied (e.g. `string(8)`), it
    is interpreted as minimum-only (min set, max unset).
    """

    kind: EnvValueKind = Field(..., description="Base kind from `type=` metadata")
    min_value: int | float | None = Field(None, description="Optional minimum bound")
    max_value: int | float | None = Field(None, description="Optional maximum bound")
    raw: str = Field(..., description="Original type string as it appeared in template")

    model_config = ConfigDict(validate_assignment=True, use_enum_values=True)

    @model_validator(mode="after")
    def validate_bounds(self) -> EnvTemplateValueType:
        bounded_kinds = {
            EnvValueKind.STRING,
            EnvValueKind.INT,
            EnvValueKind.FLOAT,
            EnvValueKind.PASSWORD,
            EnvValueKind.PASSPHRASE,
            EnvValueKind.BASE64,
            EnvValueKind.BASE64URLSAFE,
        }

        if self.kind not in bounded_kinds and (
            self.min_value is not None or self.max_value is not None
        ):
            raise ValueError(f"Bounds are not supported for type '{self.kind}'")

        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            raise ValueError("min_value cannot be greater than max_value")

        return self

    @classmethod
    def parse(cls, raw_type: str) -> EnvTemplateValueType:
        """Parse a type string into a structured value type model."""
        raw = raw_type.strip()
        match = re.fullmatch(r"([a-zA-Z][a-zA-Z0-9]*)\s*(?:\(([^)]*)\))?", raw)
        if not match:
            raise ValueError(f"Invalid type syntax: {raw_type}")

        kind_text = match.group(1).strip().lower()
        args_text = match.group(2)

        try:
            kind = EnvValueKind(kind_text)
        except ValueError as exc:
            raise ValueError(f"Unsupported type kind: {kind_text}") from exc

        min_value: int | float | None = None
        max_value: int | float | None = None

        if args_text is not None:
            min_value, max_value = cls._parse_bounds(kind, args_text)

        return cls(kind=kind, min_value=min_value, max_value=max_value, raw=raw)

    @staticmethod
    def _parse_bounds(
        kind: EnvValueKind, args_text: str
    ) -> tuple[int | float | None, int | float | None]:
        bounded_kinds = {
            EnvValueKind.STRING,
            EnvValueKind.INT,
            EnvValueKind.FLOAT,
            EnvValueKind.PASSWORD,
            EnvValueKind.PASSPHRASE,
            EnvValueKind.BASE64,
            EnvValueKind.BASE64URLSAFE,
        }
        if kind not in bounded_kinds:
            raise ValueError(f"Bounds are not supported for type '{kind.value}'")

        parts = [part.strip() for part in args_text.split(",")]
        if len(parts) == 1:
            if parts[0] == "":
                return None, None
            value = EnvTemplateValueType._coerce_bound(kind, parts[0])
            return value, None

        if len(parts) == 2:
            min_value = (
                EnvTemplateValueType._coerce_bound(kind, parts[0]) if parts[0] else None
            )
            max_value = (
                EnvTemplateValueType._coerce_bound(kind, parts[1]) if parts[1] else None
            )
            return min_value, max_value

        raise ValueError(
            f"Invalid bounds syntax for type '{kind.value}': ({args_text})"
        )

    @staticmethod
    def _coerce_bound(kind: EnvValueKind, raw_value: str) -> int | float:
        if kind == EnvValueKind.FLOAT:
            return float(raw_value)
        return int(raw_value)


class EnvTemplateVariable(BaseModel):
    """Represents one variable line from a `.env.template` file."""

    key: str = Field(..., description="Environment variable name")
    value: str = Field(
        "", description="Default value from variable assignment (left of # comment)"
    )
    recommended: str | None = Field(
        None, description="Recommended value for generated .env"
    )
    value_type: EnvTemplateValueType | None = Field(
        None, description="Parsed value type metadata"
    )
    prompt: str | None = Field(None, description="Questionary prompt message")
    instruction: str | None = Field(None, description="Questionary instruction")
    choices: list[EnvTemplateChoice] | None = Field(
        None, description="Questionary choices"
    )
    immutable: bool = Field(False, description="Whether variable is immutable")
    remember: bool = Field(
        False,
        description=(
            "Whether generated secret plaintext should be shown in end-of-run summary"
        ),
    )
    description: str | None = Field(
        None, description="Human-readable variable description"
    )
    derive: str | None = Field(
        None,
        description=(
            "Optional interpolation expression used to derive the value from "
            "other env variables"
        ),
    )
    extra_metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Additional inline metadata fields not represented by explicit attributes",
    )
    line_number: int | None = Field(
        None, description="1-based line number of this variable"
    )

    model_config = ConfigDict(validate_assignment=True, use_enum_values=True)

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        key = value.strip()
        if not key:
            raise ValueError("Variable key cannot be empty")
        return key

    @field_validator("recommended", mode="before")
    @classmethod
    def normalize_recommended(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            if normalized == "" or normalized.lower() in {"none", "null"}:
                return None
            return normalized
        return value

    @model_validator(mode="before")
    @classmethod
    def normalize_boolean_recommended(cls, values: object) -> object:
        if not isinstance(values, dict):
            return values

        recommended = values.get("recommended")
        if recommended is None or not isinstance(recommended, str):
            return values

        value_type = values.get("value_type")
        kind: EnvValueKind | None = None
        if isinstance(value_type, EnvTemplateValueType):
            kind = value_type.kind
        elif isinstance(value_type, dict):
            raw_kind = value_type.get("kind")
            if isinstance(raw_kind, EnvValueKind):
                kind = raw_kind
            elif isinstance(raw_kind, str):
                try:
                    kind = EnvValueKind(raw_kind)
                except ValueError:
                    kind = None

        if kind == EnvValueKind.BOOLEAN:
            values = dict(values)
            values["recommended"] = recommended.strip().lower()

        return values

    @model_validator(mode="after")
    def validate_recommended_value(self) -> EnvTemplateVariable:
        if self.recommended is None or self.value_type is None:
            return self

        kind = self.value_type.kind
        recommended = self.recommended

        if kind == EnvValueKind.BOOLEAN:
            normalized = recommended.strip().lower()
            if normalized not in {"true", "false"}:
                raise ValueError("Boolean recommended value must be true or false")
            return self

        if kind == EnvValueKind.MEMORY:
            if not _MEMORY_PATTERN.fullmatch(recommended):
                raise ValueError(
                    "Memory recommended value must match format <number><K|M|G|T>"
                )

        elif kind == EnvValueKind.IP:
            ipaddress.ip_address(recommended)

        elif kind == EnvValueKind.PORT:
            port = int(recommended)
            if port < 1 or port > 65535:
                raise ValueError("Port recommended value must be between 1 and 65535")

        elif kind == EnvValueKind.INT:
            value = int(recommended)
            self._validate_numeric_bounds(float(value))

        elif kind == EnvValueKind.FLOAT:
            value = float(recommended)
            self._validate_numeric_bounds(value)

        elif kind in {
            EnvValueKind.STRING,
            EnvValueKind.PASSWORD,
            EnvValueKind.PASSPHRASE,
            EnvValueKind.BASE64,
            EnvValueKind.BASE64URLSAFE,
        }:
            length = len(recommended)
            self._validate_numeric_bounds(float(length))

        return self

    def _validate_numeric_bounds(self, value: float) -> None:
        if self.value_type is None:
            return

        if self.value_type.min_value is not None and value < float(
            self.value_type.min_value
        ):
            raise ValueError("Recommended value is below minimum bound")

        if self.value_type.max_value is not None and value > float(
            self.value_type.max_value
        ):
            raise ValueError("Recommended value is above maximum bound")


class ParsedEnvTemplate(BaseModel):
    """Top-level parsed output for a `.env.template` file."""

    metadata: EnvTemplateMetadata = Field(default_factory=EnvTemplateMetadata)
    variables: list[EnvTemplateVariable] = Field(default_factory=list)
    warnings: list[EnvTemplateWarning] = Field(default_factory=list)
    source_path: str | None = Field(None, description="Path to source template file")
