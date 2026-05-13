"""Parser for `.env.template` files with best-effort diagnostics."""

from __future__ import annotations

import re
from pathlib import Path

from models import (
    EnvTemplateChoice,
    EnvTemplateMetadata,
    EnvTemplateValueType,
    EnvTemplateVariable,
    EnvTemplateWarning,
    ParsedEnvTemplate,
)


class EnvTemplateParsingError(Exception):
    """Raised when a template cannot be loaded for parsing."""


class EnvTemplateParser:
    """Parses `.env.template` metadata and variable inline annotations."""

    _COMPUTE_RESOLVER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

    def __init__(self, file_path: Path | str) -> None:
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

    def parse(self) -> ParsedEnvTemplate:
        """Parse template into structured model with non-fatal warnings."""
        try:
            lines = self.file_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise EnvTemplateParsingError(
                f"Unable to read file: {self.file_path}"
            ) from exc

        warnings: list[EnvTemplateWarning] = []
        metadata = self._parse_metadata(lines, warnings)
        variables = self._parse_variables(lines, warnings)

        return ParsedEnvTemplate(
            metadata=metadata,
            variables=variables,
            warnings=warnings,
            source_path=str(self.file_path),
        )

    def _parse_metadata(
        self, lines: list[str], warnings: list[EnvTemplateWarning]
    ) -> EnvTemplateMetadata:
        in_metadata = False
        metadata_map: dict[str, str] = {}

        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped == "# METADATA --- START":
                in_metadata = True
                continue

            if stripped == "# METADATA --- END":
                break

            if not in_metadata or not stripped or stripped.startswith("#"):
                continue

            if "=" not in stripped:
                warnings.append(
                    EnvTemplateWarning(
                        line=line_number,
                        field="metadata",
                        message="Metadata line is missing '=' delimiter",
                        raw_fragment=stripped,
                    )
                )
                continue

            key, value = stripped.split("=", 1)
            metadata_map[key.strip().lower()] = value.strip()

        required: bool | None = None
        if "required" in metadata_map:
            required = self._parse_bool(metadata_map["required"])
            if required is None:
                warnings.append(
                    EnvTemplateWarning(
                        field="required",
                        message="Invalid boolean in metadata 'required' field",
                        raw_fragment=metadata_map["required"],
                    )
                )

        extra = {
            key: value
            for key, value in metadata_map.items()
            if key not in {"description", "required"}
        }

        return EnvTemplateMetadata(
            description=metadata_map.get("description"),
            required=required,
            extra=extra,
        )

    def _parse_variables(
        self, lines: list[str], warnings: list[EnvTemplateWarning]
    ) -> list[EnvTemplateVariable]:
        variables: list[EnvTemplateVariable] = []
        in_metadata = False

        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()

            if stripped == "# METADATA --- START":
                in_metadata = True
                continue

            if stripped == "# METADATA --- END":
                in_metadata = False
                continue

            if in_metadata or not stripped or stripped.startswith("#"):
                continue

            if "=" not in line:
                warnings.append(
                    EnvTemplateWarning(
                        line=line_number,
                        field="variable",
                        message="Variable line is missing '=' delimiter",
                        raw_fragment=line,
                    )
                )
                continue

            key_part, rhs = line.split("=", 1)
            key = key_part.strip()
            if not key:
                warnings.append(
                    EnvTemplateWarning(
                        line=line_number,
                        field="key",
                        message="Variable key is empty",
                        raw_fragment=line,
                    )
                )
                continue

            value_part, inline_comment = self._split_value_comment(rhs)
            metadata_map = self._parse_inline_metadata(
                inline_comment, line_number, warnings
            )
            variable = self._build_variable(
                key=key,
                value=value_part.strip(),
                metadata_map=metadata_map,
                line_number=line_number,
                warnings=warnings,
            )
            if variable is not None:
                variables.append(variable)

        return variables

    @staticmethod
    def _split_value_comment(rhs: str) -> tuple[str, str]:
        if "#" not in rhs:
            return rhs.strip(), ""
        value, comment = rhs.split("#", 1)
        return value.strip(), comment.strip()

    def _parse_inline_metadata(
        self,
        inline_comment: str,
        line_number: int,
        warnings: list[EnvTemplateWarning],
    ) -> dict[str, str]:
        if not inline_comment:
            return {}

        fragments = [
            fragment.strip()
            for fragment in self._split_outside_backticks(inline_comment)
            if fragment.strip()
        ]
        metadata: dict[str, str] = {}

        for fragment in fragments:
            if "=" not in fragment:
                warnings.append(
                    EnvTemplateWarning(
                        line=line_number,
                        field="inline_metadata",
                        message="Inline metadata fragment is missing '=' delimiter",
                        raw_fragment=fragment,
                    )
                )
                continue

            key, value = fragment.split("=", 1)
            normalized_key = key.strip().lower()

            if normalized_key in metadata:
                warnings.append(
                    EnvTemplateWarning(
                        line=line_number,
                        field=normalized_key,
                        message="Duplicate inline metadata key; last value wins",
                        raw_fragment=fragment,
                    )
                )

            metadata[normalized_key] = value.strip()

        return metadata

    def _build_variable(
        self,
        key: str,
        value: str,
        metadata_map: dict[str, str],
        line_number: int,
        warnings: list[EnvTemplateWarning],
    ) -> EnvTemplateVariable | None:
        recommended = metadata_map.get("recommended")
        prompt = metadata_map.get("prompt")
        instruction = metadata_map.get("instruction")
        description = metadata_map.get("description")
        derive = metadata_map.get("derive")

        immutable = False
        if "immutable" in metadata_map:
            parsed_immutable = self._parse_bool(metadata_map["immutable"])
            if parsed_immutable is None:
                warnings.append(
                    EnvTemplateWarning(
                        line=line_number,
                        field="immutable",
                        message="Invalid boolean value for immutable",
                        raw_fragment=metadata_map["immutable"],
                    )
                )
            else:
                immutable = parsed_immutable

        remember = False
        if "remember" in metadata_map:
            parsed_remember = self._parse_bool(metadata_map["remember"])
            if parsed_remember is None:
                warnings.append(
                    EnvTemplateWarning(
                        line=line_number,
                        field="remember",
                        message="Invalid boolean value for remember",
                        raw_fragment=metadata_map["remember"],
                    )
                )
            else:
                remember = parsed_remember

        value_type: EnvTemplateValueType | None = None
        if "type" in metadata_map:
            try:
                value_type = EnvTemplateValueType.parse(metadata_map["type"])
            except ValueError as exc:
                warnings.append(
                    EnvTemplateWarning(
                        line=line_number,
                        field="type",
                        message=str(exc),
                        raw_fragment=metadata_map["type"],
                    )
                )

        choices: list[EnvTemplateChoice] | None = None
        if "choices" in metadata_map:
            choices = self._parse_choices(
                metadata_map["choices"], line_number, warnings
            )

        compute_hint = metadata_map.get("compute")
        if compute_hint is not None:
            normalized_compute = compute_hint.strip().lower()
            if not self._COMPUTE_RESOLVER_PATTERN.fullmatch(normalized_compute):
                warnings.append(
                    EnvTemplateWarning(
                        line=line_number,
                        field="compute",
                        message=(
                            "Invalid compute resolver format; use a simple "
                            "identifier like uid or docker_gid"
                        ),
                        raw_fragment=compute_hint,
                    )
                )

        if derive is not None and not derive.strip():
            warnings.append(
                EnvTemplateWarning(
                    line=line_number,
                    field="derive",
                    message="Derive expression is empty; ignoring derive metadata",
                    raw_fragment=derive,
                )
            )
            derive = None

        if derive and compute_hint is not None:
            warnings.append(
                EnvTemplateWarning(
                    line=line_number,
                    field="derive",
                    message=(
                        "Both derive and compute are declared; derive takes "
                        "precedence"
                    ),
                    raw_fragment=f"derive={derive}",
                )
            )

        extra_metadata = {
            k: v
            for k, v in metadata_map.items()
            if k
            not in {
                "recommended",
                "type",
                "prompt",
                "instruction",
                "choices",
                "immutable",
                "remember",
                "description",
            }
        }

        try:
            return EnvTemplateVariable(
                key=key,
                value=value,
                recommended=recommended,
                value_type=value_type,
                prompt=prompt,
                instruction=instruction,
                choices=choices,
                immutable=immutable,
                remember=remember,
                description=description,
                derive=derive,
                extra_metadata=extra_metadata,
                line_number=line_number,
            )
        except ValueError as exc:
            warnings.append(
                EnvTemplateWarning(
                    line=line_number,
                    field="variable",
                    message=f"Variable validation failed: {exc}",
                    raw_fragment=key,
                )
            )
            return EnvTemplateVariable(
                key=key,
                value=value,
                recommended=None,
                value_type=value_type,
                prompt=prompt,
                instruction=instruction,
                choices=choices,
                immutable=immutable,
                remember=remember,
                description=description,
                derive=derive,
                extra_metadata=extra_metadata,
                line_number=line_number,
            )

    def _parse_choices(
        self,
        raw_choices: str,
        line_number: int,
        warnings: list[EnvTemplateWarning],
    ) -> list[EnvTemplateChoice]:
        raw = raw_choices.strip()
        if not raw.startswith("[") or not raw.endswith("]"):
            warnings.append(
                EnvTemplateWarning(
                    line=line_number,
                    field="choices",
                    message="Choices must be enclosed in [ ... ]",
                    raw_fragment=raw_choices,
                )
            )
            return []

        content = raw[1:-1].strip()
        if not content:
            return []

        items = self._split_top_level(content)
        parsed: list[EnvTemplateChoice] = []
        for item in items:
            choice = self._parse_choice_item(item, line_number, warnings)
            if choice is not None:
                parsed.append(choice)

        return parsed

    def _parse_choice_item(
        self,
        raw_item: str,
        line_number: int,
        warnings: list[EnvTemplateWarning],
    ) -> EnvTemplateChoice | None:
        token = raw_item.strip()
        if not token:
            return None

        value = token
        attrs_text = ""

        if token.endswith(")") and "(" in token:
            start = token.rfind("(")
            if start > 0:
                value = token[:start].strip()
                attrs_text = token[start + 1 : -1].strip()

        attrs: dict[str, str] = self._parse_choice_attrs(attrs_text)

        default: bool | None = None
        if "default" in attrs:
            default = self._parse_bool(attrs["default"])
            if default is None:
                warnings.append(
                    EnvTemplateWarning(
                        line=line_number,
                        field="choices.default",
                        message="Invalid boolean for choice default",
                        raw_fragment=attrs["default"],
                    )
                )

        return EnvTemplateChoice(
            value=value,
            description=attrs.get("description"),
            default=default,
        )

    # Known attribute keys that may appear inside a choice's ( … ) block.
    _CHOICE_ATTR_RE = re.compile(r"\b(description|default)\s*=")

    @classmethod
    def _parse_choice_attrs(cls, attrs_text: str) -> dict[str, str]:
        """Parse choice attributes from the text inside the parentheses.

        Values are captured as everything between one ``key=`` anchor and the
        next, so commas and any other punctuation inside a description are
        preserved verbatim.
        """
        if not attrs_text:
            return {}
        matches = list(cls._CHOICE_ATTR_RE.finditer(attrs_text))
        attrs: dict[str, str] = {}
        for i, match in enumerate(matches):
            key = match.group(1).lower()
            val_start = match.end()
            val_end = (
                matches[i + 1].start() if i + 1 < len(matches) else len(attrs_text)
            )
            attrs[key] = attrs_text[val_start:val_end].rstrip(", ").strip()
        return attrs

    @staticmethod
    def _split_outside_backticks(text: str) -> list[str]:
        """Split *text* on ``|`` but ignore ``|`` characters inside backtick spans."""
        items: list[str] = []
        current: list[str] = []
        in_backtick = False
        for char in text:
            if char == "`":
                in_backtick = not in_backtick
            if char == "|" and not in_backtick:
                items.append("".join(current))
                current = []
            else:
                current.append(char)
        items.append("".join(current))
        return items

    @staticmethod
    def _split_top_level(text: str) -> list[str]:
        items: list[str] = []
        current: list[str] = []
        depth = 0
        for char in text:
            if char == "(":
                depth += 1
            elif char == ")":
                depth = max(0, depth - 1)

            if char == "," and depth == 0:
                item = "".join(current).strip()
                if item:
                    items.append(item)
                current = []
                continue

            current.append(char)

        tail = "".join(current).strip()
        if tail:
            items.append(tail)

        return items

    @staticmethod
    def _parse_bool(value: str) -> bool | None:
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y"}:
            return True
        if normalized in {"0", "false", "no", "n"}:
            return False
        return None
