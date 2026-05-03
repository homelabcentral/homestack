"""Parser for extracting and validating YAML front matter from readme files."""

import re
from pathlib import Path

import yaml
from models import ReadmeFrontMatter, Step
from pydantic import ValidationError


class ParsingError(Exception):
    """Raised when front matter parsing fails."""

    pass


class ReadmeFrontMatterParser:
    """Parses and validates YAML front matter from markdown readme files.

    This parser extracts front matter (YAML between --- delimiters) from markdown files
    and validates it against the ReadmeFrontMatter Pydantic model.

    Example:
        parser = ReadmeFrontMatterParser("path/to/readme.md")
        front_matter = parser.parse()
        print(front_matter.project_name)
    """

    def __init__(self, file_path: Path | str) -> None:
        """Initialize the parser with a file path.

        Args:
            file_path: Path to the markdown file containing front matter.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

    def parse(self) -> ReadmeFrontMatter:
        """Extract and parse YAML front matter from the file.

        Returns:
            ReadmeFrontMatter: Parsed and validated front matter.

        Raises:
            ParsingError: If front matter is missing, malformed, or fails model validation.
        """
        try:
            front_matter_str = self._extract_front_matter_str()
            front_matter_str = self._sanitize_common_frontmatter_issues(
                front_matter_str
            )
            front_matter_dict = self._parse_yaml(front_matter_str)
            self._reject_legacy_step_keys(front_matter_dict)
            front_matter_dict = self._normalize_legacy_keys(front_matter_dict)
            front_matter = self._convert_steps(front_matter_dict)
            return ReadmeFrontMatter(**front_matter)
        except ParsingError:
            raise
        except (yaml.YAMLError, ValidationError) as e:
            raise ParsingError(f"Failed to parse {self.file_path}: {e}") from e

    def _reject_legacy_step_keys(self, data: dict) -> None:
        """Reject legacy hyphenated step keys to enforce underscore naming."""
        if not isinstance(data, dict):
            return

        legacy_keys = [
            "pre-install-steps",
            "post-install-steps",
            "post-setup-steps",
        ]
        present = [key for key in legacy_keys if key in data]
        if present:
            raise ParsingError(
                "Legacy step key(s) are not allowed: "
                f"{', '.join(present)}. Use pre_install_steps/post_install_steps/post_setup_steps."
            )

    def _sanitize_common_frontmatter_issues(self, content: str) -> str:
        """Sanitize recurring formatting issues seen in project readmes.

        This keeps the parser tolerant of legacy front matter while preserving
        existing strict model validation.
        """
        # Some readmes contain ready_to_deploy like `|true,false|`, which is not valid YAML.
        content = re.sub(
            r"(ready_to_deploy:\s*)\|?(true|false)\s*,\s*(true|false)\|?",
            r"\1\2",
            content,
            flags=re.IGNORECASE,
        )

        lines = content.split("\n")
        sanitized: list[str] = []
        for line in lines:
            # Normalize mis-indented wrapped step entries like "    - step:".
            if line.startswith("    - step:"):
                sanitized.append("  - step:")
            else:
                sanitized.append(line)
        return "\n".join(sanitized)

    def _normalize_legacy_keys(self, data: dict) -> dict:
        """Normalize legacy front matter keys/structures to current schema.

        This unwraps legacy nested ``config_file`` entries when present.
        """
        if not isinstance(data, dict):
            return {}

        normalized = dict(data)

        config_files = normalized.get("config_files")
        if isinstance(config_files, list):
            unwrapped_configs: list[dict | object] = []
            for entry in config_files:
                if isinstance(entry, dict) and isinstance(
                    entry.get("config_file"), dict
                ):
                    unwrapped_configs.append(entry["config_file"])
                else:
                    unwrapped_configs.append(entry)
            normalized["config_files"] = unwrapped_configs

        ready_to_deploy = normalized.get("ready_to_deploy")
        if isinstance(ready_to_deploy, str):
            lowered = ready_to_deploy.strip().lower()
            if lowered in {"true", "yes", "1"}:
                normalized["ready_to_deploy"] = True
            elif lowered in {"false", "no", "0"}:
                normalized["ready_to_deploy"] = False

        return normalized

    def _extract_front_matter_str(self) -> str:
        """Extract YAML front matter string between --- delimiters.

        Returns:
            str: Raw YAML front matter content.

        Raises:
            ParsingError: If front matter delimiters are not found.
        """
        with open(self.file_path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")
        if not lines or lines[0].strip() != "---":
            raise ParsingError(
                f"File {self.file_path} does not start with '---' delimiter"
            )

        # Find the closing delimiter
        closing_index = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                closing_index = i
                break

        if closing_index is None:
            raise ParsingError(
                f"File {self.file_path} does not have closing '---' delimiter"
            )

        return "\n".join(lines[1:closing_index])

    def _parse_yaml(self, yaml_str: str) -> dict:
        """Parse YAML string into a dictionary.

        Args:
            yaml_str: Raw YAML content.

        Returns:
            dict: Parsed YAML as a dictionary.

        Raises:
            yaml.YAMLError: If YAML parsing fails.
        """
        return yaml.safe_load(yaml_str) or {}

    def _convert_steps(self, data: dict) -> dict:
        """Convert step dictionaries to Step objects where applicable.

        Args:
            data: Parsed front matter dictionary.

        Returns:
            dict: Dictionary with Step objects converted where needed.
        """
        step_keys = ["pre_install_steps", "post_install_steps", "post_setup_steps"]

        for key in step_keys:
            if key in data and data[key] is not None:
                steps_list = data[key]
                if isinstance(steps_list, list):
                    converted_steps: list[Step | object] = []
                    for index, raw_step in enumerate(steps_list, start=1):
                        step_payload = raw_step
                        if isinstance(raw_step, dict) and isinstance(
                            raw_step.get("step"), dict
                        ):
                            step_payload = raw_step["step"]

                        if isinstance(step_payload, dict):
                            # Some legacy step blocks omit `number`; infer sequentially.
                            step_payload = {"number": index, **step_payload}
                            converted_steps.append(Step(**step_payload))
                        else:
                            converted_steps.append(step_payload)

                    data[key] = converted_steps

        return data
