"""Tests for ReadmeFrontMatterParser."""

import tempfile
from pathlib import Path

import pytest
from parsers import ParsingError, ReadmeFrontMatterParser


class TestReadmeFrontMatterParser:
    """Test cases for ReadmeFrontMatterParser."""

    def test_parser_init_with_valid_file(self, temp_readme_file):
        """Test parser initialization with existing file."""
        parser = ReadmeFrontMatterParser(temp_readme_file)
        assert parser.file_path == temp_readme_file

    def test_parser_init_with_string_path(self, temp_readme_file):
        """Test parser initialization with string path."""
        parser = ReadmeFrontMatterParser(str(temp_readme_file))
        assert isinstance(parser.file_path, Path)

    def test_parser_init_with_nonexistent_file(self):
        """Test parser raises FileNotFoundError for nonexistent file."""
        with pytest.raises(FileNotFoundError):
            ReadmeFrontMatterParser("/nonexistent/path/readme.md")

    def test_parse_valid_complete_front_matter(self, temp_readme_file):
        """Test parsing valid front matter with all fields."""
        parser = ReadmeFrontMatterParser(temp_readme_file)
        front_matter = parser.parse()

        assert front_matter.author == "Test Author"
        assert front_matter.project_name == "Test Project"
        assert front_matter.project_description == "Test Description"
        assert front_matter.project_source == "https://github.com/test/project"
        assert front_matter.project_website == "https://example.com"
        assert front_matter.project_status == "Active"
        assert len(front_matter.stable_images) == 2
        assert front_matter.ready_to_deploy is True

    def test_parse_minimal_front_matter(self, minimal_readme_file):
        """Test parsing front matter with only required fields."""
        parser = ReadmeFrontMatterParser(minimal_readme_file)
        front_matter = parser.parse()

        assert front_matter.author == "Minimal Author"
        assert front_matter.project_name == "Minimal Project"
        assert front_matter.project_source == "https://github.com/minimal/project"
        assert len(front_matter.stable_images) == 1
        assert front_matter.ready_to_deploy is True
        assert front_matter.project_description is None
        assert front_matter.warning is None

    def test_parse_date_object_conversion(self, date_object_readme_file):
        """Test that date objects are converted to strings."""
        parser = ReadmeFrontMatterParser(date_object_readme_file)
        front_matter = parser.parse()

        # Even if YAML returns a date object, it should be converted to string
        assert isinstance(front_matter.date, str)
        assert isinstance(front_matter.last_updated, str)

    def test_parse_malformed_yaml(self, malformed_yaml_file):
        """Test parsing raises ParsingError for malformed YAML."""
        parser = ReadmeFrontMatterParser(malformed_yaml_file)
        with pytest.raises(ParsingError):
            parser.parse()

    def test_parse_missing_closing_delimiter(self, missing_delimiter_file):
        """Test parsing raises ParsingError without closing delimiter."""
        parser = ReadmeFrontMatterParser(missing_delimiter_file)
        with pytest.raises(ParsingError) as exc_info:
            parser.parse()
        assert (
            "closing" in str(exc_info.value).lower()
            or "delimiter" in str(exc_info.value).lower()
        )

    def test_parse_missing_opening_delimiter(self):
        """Test parsing raises ParsingError without opening delimiter."""
        import tempfile

        content = """author: Test Author
project_name: Test Project
---
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            parser = ReadmeFrontMatterParser(temp_path)
            with pytest.raises(ParsingError) as exc_info:
                parser.parse()
            assert "does not start with" in str(exc_info.value)
        finally:
            Path(temp_path).unlink()

    def test_parse_missing_required_fields(self):
        """Test parsing raises ParsingError for missing required fields."""
        import tempfile

        content = """---
author: Test Author
project_name: Test Project
# Missing required fields
---
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            parser = ReadmeFrontMatterParser(temp_path)
            with pytest.raises(ParsingError):
                parser.parse()
        finally:
            Path(temp_path).unlink()

    def test_parse_with_steps(self, temp_readme_file):
        """Test parsing front matter with step definitions."""
        parser = ReadmeFrontMatterParser(temp_readme_file)
        front_matter = parser.parse()

        assert front_matter.pre_install_steps is not None
        assert len(front_matter.pre_install_steps) == 1
        assert front_matter.pre_install_steps[0].number == 1
        assert front_matter.pre_install_steps[0].description == "Setup step"
        assert front_matter.pre_install_steps[0].todo == "mkdir -p /data"

    def test_extract_front_matter_str(self, temp_readme_file):
        """Test extracting raw YAML front matter string."""
        parser = ReadmeFrontMatterParser(temp_readme_file)
        yaml_str = parser._extract_front_matter_str()

        assert "author: Test Author" in yaml_str
        assert "project_name: Test Project" in yaml_str
        assert "---" not in yaml_str  # Delimiters should not be in extracted content

    def test_parse_yaml_valid(self, temp_readme_file):
        """Test YAML parsing."""
        parser = ReadmeFrontMatterParser(temp_readme_file)
        yaml_str = parser._extract_front_matter_str()
        parsed = parser._parse_yaml(yaml_str)

        assert isinstance(parsed, dict)
        assert "author" in parsed
        assert parsed["project_name"] == "Test Project"

    def test_parse_yaml_empty_string(self):
        """Test YAML parsing with empty string."""
        parser = ReadmeFrontMatterParser
        parsed = parser._parse_yaml(None, "")
        assert parsed == {}

    def test_convert_steps_in_front_matter(self, temp_readme_file):
        """Test step conversion during parsing."""
        parser = ReadmeFrontMatterParser(temp_readme_file)
        front_matter = parser.parse()

        # All step types should be converted
        assert front_matter.pre_install_steps is not None
        assert front_matter.post_install_steps is not None
        assert all(hasattr(step, "number") for step in front_matter.pre_install_steps)

    def test_parser_handles_utf8_encoding(self):
        """Test parser handles UTF-8 encoded files."""
        import tempfile

        content = """---
author: Tëst Åuthör
project_name: Tëst Prøjëct
project_source: https://github.com/test/project
stable_images:
  - image:1.0.0
date: 2026-04-23
last_updated: 2026-04-23
supported_architecture:
    - x86_64
    - arm64
ready_to_deploy: true
---
# Tëst"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        ) as f:
            f.write(content)
            temp_path = f.name

        try:
            parser = ReadmeFrontMatterParser(temp_path)
            front_matter = parser.parse()
            assert "ë" in front_matter.author
        finally:
            Path(temp_path).unlink()

    def test_parse_with_config_files(self, temp_readme_file):
        """Test parsing front matter with config file definitions."""
        parser = ReadmeFrontMatterParser(temp_readme_file)
        front_matter = parser.parse()

        assert front_matter.config_files is not None
        assert len(front_matter.config_files) > 0
        assert front_matter.config_files[0].path == "config.yml"
        assert front_matter.config_files[0].constant is True

    def test_parsing_preserves_data_types(self, temp_readme_file):
        """Test that parsing preserves correct data types."""
        parser = ReadmeFrontMatterParser(temp_readme_file)
        front_matter = parser.parse()

        assert isinstance(front_matter.author, str)
        assert isinstance(front_matter.ready_to_deploy, bool)
        assert isinstance(front_matter.stable_images, list)
        assert isinstance(front_matter.supported_architecture, list)

        def test_parse_handles_wrapped_blocks_with_underscored_step_keys(self):
            """Wrapped front matter blocks should parse when using underscored step keys."""
            content = """---
author: Homelab Central
project_name: Gatus
project_description: Status page
project_source: https://github.com/TwiN/gatus
stable_images:
    - ghcr.io/twin/gatus:stable
date: 2026-04-23
last_updated: 2026-04-23
config_files:
    - config_file:
            path: config/config.yml
            constant: true
pre_install_steps:
    - step:
            description: Configure
            todo: Edit config
post_install_steps:
    - step:
            description: Verify
            todo: Check service
supported_architecture:
    - x86_64
    - arm64
ready_to_deploy: true
---
"""
            with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
                f.write(content)
                temp_path = Path(f.name)

            try:
                parsed = ReadmeFrontMatterParser(temp_path).parse()
                assert parsed.project_name == "Gatus"
                assert parsed.config_files is not None
                assert parsed.config_files[0].path == "config/config.yml"
                assert parsed.pre_install_steps is not None
                assert parsed.pre_install_steps[0].number == 1
                assert parsed.post_install_steps is not None
                assert parsed.post_install_steps[0].number == 1
            finally:
                temp_path.unlink(missing_ok=True)

            def test_parse_rejects_legacy_hyphenated_step_keys(self):
                """Legacy hyphenated step keys should be rejected."""
                content = """---
            author: Homelab Central
            project_name: Legacy
            project_source: https://github.com/example/legacy
            stable_images:
              - example:1.0.0
            date: 2026-04-23
            last_updated: 2026-04-23
            pre-install-steps:
              - step:
                  description: Legacy key
                  todo: Replace key
                        supported_architecture:
                            - x86_64
                            - arm64
            ready_to_deploy: true
            ---
            """
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".md", delete=False
                ) as f:
                    f.write(content)
                    temp_path = Path(f.name)

                try:
                    with pytest.raises(ParsingError) as exc_info:
                        ReadmeFrontMatterParser(temp_path).parse()
                    assert "Legacy step key" in str(exc_info.value)
                finally:
                    temp_path.unlink(missing_ok=True)

        def test_parse_sanitizes_pipe_ready_to_deploy_and_step_indentation(self):
            """Common malformed snippets should be sanitized before parsing."""
            content = """---
author: Homelab Central
project_name: StirlingPDF
project_description: PDF toolkit
project_source: https://github.com/Stirling-Tools/Stirling-PDF
stable_images:
    - stirlingtools/stirling-pdf:latest
date: 2026-04-23
last_updated: 2026-04-23
pre_install_steps:
    - step:
            description: Set username
            todo: Configure user
        - step:
            description: Set password
            todo: Configure password
supported_architecture:
    - x86_64
    - arm64
ready_to_deploy: |true,false|
---
"""
            with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
                f.write(content)
                temp_path = Path(f.name)

            try:
                parsed = ReadmeFrontMatterParser(temp_path).parse()
                assert parsed.project_name == "StirlingPDF"
                assert parsed.ready_to_deploy is True
                assert parsed.pre_install_steps is not None
                assert len(parsed.pre_install_steps) == 2
                assert parsed.pre_install_steps[1].number == 2
            finally:
                temp_path.unlink(missing_ok=True)
