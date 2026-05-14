"""Tests for Readme server metadata collection utility."""

from pathlib import Path

from server.readme import Readme


class TestReadmeGenerator:
    """Test cases for Readme metadata collector."""

    def test_readme_init_with_custom_path(self, temp_project_dir):
        """Test Readme initialization with custom workspace root."""
        readme_gen = Readme(workspace_root=temp_project_dir)
        assert readme_gen.workspace_root == temp_project_dir

    def test_readme_init_without_path(self, temp_project_dir):
        """Test Readme initialization with None uses default root_dir."""
        # When workspace_root is None, it uses the settings root_dir
        # We test that it initializes correctly with None and results in a Path
        readme_gen = Readme(workspace_root=None)
        assert isinstance(readme_gen.workspace_root, Path)
        assert readme_gen.workspace_root.is_absolute()

    def test_collect_finds_project_readmes(self, temp_project_dir):
        """Test collect() finds all project readme files."""
        readme_gen = Readme(workspace_root=temp_project_dir)
        readmes = readme_gen.collect()

        assert len(readmes) == 2
        assert readmes[0].project_name == "Project 1"
        assert readmes[1].project_name == "Project 2"

    def test_collect_returns_parsed_front_matter(self, temp_project_dir):
        """Test collect() returns ReadmeFrontMatter instances."""
        readme_gen = Readme(workspace_root=temp_project_dir)
        readmes = readme_gen.collect()

        for readme in readmes:
            assert hasattr(readme, "project_name")
            assert hasattr(readme, "author")
            assert hasattr(readme, "ready_to_deploy")

    def test_collect_skips_missing_readmes(self, tmp_path):
        """Test collect() skips directories without readme.md."""
        # Create a project directory without readme
        project_dir = tmp_path / "02.project_no_readme"
        project_dir.mkdir()

        readme_gen = Readme(workspace_root=tmp_path)
        readmes = readme_gen.collect()

        # Should not crash and return empty list
        assert isinstance(readmes, list)

    def test_collect_skips_non_project_dirs(self, tmp_path):
        """Test collect() only processes numbered directories."""
        # Create non-project directories
        (tmp_path / "docs").mkdir()
        (tmp_path / "scripts").mkdir()
        (tmp_path / "invalid").mkdir()

        # Create a valid project directory
        project_dir = tmp_path / "00.test"
        project_dir.mkdir()
        readme_file = project_dir / "readme.md"
        readme_file.write_text(
            """---
author: Test
project_name: Test
project_source: https://github.com/test/test
stable_images:
  - test:1.0.0
date: 2026-04-23
last_updated: 2026-04-23
supported_architecture:
    - x86_64
    - arm64
ready_to_deploy: true
---
# Test"""
        )

        readme_gen = Readme(workspace_root=tmp_path)
        readmes = readme_gen.collect()

        # Should only find the one valid project
        assert len(readmes) == 1
        assert readmes[0].project_name == "Test"

    def test_is_project_dir_valid(self):
        """Test _is_project_dir() recognizes valid project directories."""
        assert Readme._is_project_dir("00.pihole")
        assert Readme._is_project_dir("01.traefik")
        assert Readme._is_project_dir("99.project")

    def test_is_project_dir_invalid(self):
        """Test _is_project_dir() rejects invalid directory names."""
        assert not Readme._is_project_dir("pihole")
        assert not Readme._is_project_dir("00_pihole")
        assert not Readme._is_project_dir("project-00")
        assert not Readme._is_project_dir("docs")
        assert not Readme._is_project_dir("")  # Empty string
        assert not Readme._is_project_dir(".")  # Just a dot

    def test_is_project_dir_edge_cases(self):
        """Test _is_project_dir() with edge cases."""
        assert not Readme._is_project_dir("0.project")  # Single digit
        assert not Readme._is_project_dir("000.project")  # Three digits
        assert not Readme._is_project_dir(".project")  # No digit

    def test_collect_handles_parsing_errors_gracefully(self, tmp_path):
        """Test collect() handles parsing errors gracefully."""
        # Create a project with malformed readme
        project_dir = tmp_path / "00.bad_project"
        project_dir.mkdir()
        readme_file = project_dir / "readme.md"
        readme_file.write_text(
            """---
author: Test
# Missing required fields
---
# Bad"""
        )

        # Create a valid project
        valid_dir = tmp_path / "01.good_project"
        valid_dir.mkdir()
        valid_readme = valid_dir / "readme.md"
        valid_readme.write_text(
            """---
author: Good
project_name: Good Project
project_source: https://github.com/good/project
stable_images:
  - good:1.0.0
date: 2026-04-23
last_updated: 2026-04-23
supported_architecture:
    - x86_64
    - arm64
ready_to_deploy: true
---
# Good"""
        )

        readme_gen = Readme(workspace_root=tmp_path)
        readmes = readme_gen.collect()

        # Should collect only the valid one
        assert len(readmes) == 1
        assert readmes[0].project_name == "Good Project"

    def test_collect_processes_directories_in_order(self, tmp_path):
        """Test collect() processes directories in sorted order."""
        # Create projects in reverse alphabetical order
        for i in range(3):
            project_dir = tmp_path / f"0{i}.project{i}"
            project_dir.mkdir()
            readme_file = project_dir / "readme.md"
            readme_file.write_text(
                f"""---
author: Author {i}
project_name: Project {i}
project_source: https://github.com/test/project{i}
stable_images:
  - image:1.0.0
date: 2026-04-23
last_updated: 2026-04-23
supported_architecture:
    - x86_64
    - arm64
ready_to_deploy: true
---
# Project {i}"""
            )

        readme_gen = Readme(workspace_root=tmp_path)
        readmes = readme_gen.collect()

        # Should be in order
        assert readmes[0].project_name == "Project 0"
        assert readmes[1].project_name == "Project 1"
        assert readmes[2].project_name == "Project 2"

        def test_collect_returns_models_not_json(self, temp_project_dir):
            """Collect should return parsed model instances directly."""
            readme_gen = Readme(workspace_root=temp_project_dir)
            readmes = readme_gen.collect()

            assert len(readmes) == 2
            assert all(hasattr(item, "model_dump") for item in readmes)
