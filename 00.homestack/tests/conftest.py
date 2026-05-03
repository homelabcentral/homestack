"""Pytest configuration and shared fixtures for parser tests."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_readme_file():
    """Create a temporary readme file with valid front matter."""
    content = """---
author: Test Author
project_name: Test Project
project_description: Test Description
project_source: https://github.com/test/project
project_website: https://example.com
project_docs: https://docs.example.com
project_status: Active
stable_images:
  - test:1.0.0
  - test:latest
stable_versions:
  - 1.0.0
latest_images:
  - test:2.0.0
latest_versions:
  - 2.0.0
warning: This is a test warning
date: 2026-04-23
last_updated: 2026-04-23
required_env_files:
  - test.env
config_files:
  - path: config.yml
    constant: true
    keys:
      key1: type1
pre_install_steps:
  - number: 1
    description: Setup step
    todo: mkdir -p /data
post_install_steps:
  - number: 1
    description: Configure step
    todo: chmod 755 /data
post_setup_steps:
  - number: 1
    description: Final step
    todo: systemctl restart service
supported_architecture:
  - amd64
  - arm64
ready_to_deploy: true
---

# Test Readme

This is a test readme file with front matter.
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    yield Path(temp_path)

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def minimal_readme_file():
    """Create a temporary readme with only required fields."""
    content = """---
author: Minimal Author
project_name: Minimal Project
project_source: https://github.com/minimal/project
stable_images:
  - minimal:1.0.0
date: 2026-04-23
last_updated: 2026-04-23
supported_architecture:
  - amd64
ready_to_deploy: true
---

# Minimal Readme
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    yield Path(temp_path)

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def malformed_yaml_file():
    """Create a readme with malformed YAML."""
    content = """---
author: Test
project_name: Test: Malformed: Content
missing required fields
---

# Test
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    yield Path(temp_path)

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def missing_delimiter_file():
    """Create a readme without closing front matter delimiter."""
    content = """---
author: Test Author
project_name: Test Project
project_source: https://github.com/test/project

# No closing delimiter
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    yield Path(temp_path)

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def date_object_readme_file():
    """Create a readme where YAML parser returns date objects."""
    content = """---
author: Test Author
project_name: Test Project
project_source: https://github.com/test/project
stable_images:
  - test:1.0.0
date: 2026-04-23
last_updated: 2026-04-23
supported_architecture:
  - amd64
ready_to_deploy: true
---

# Test with date objects
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = f.name

    yield Path(temp_path)

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory structure with multiple readmes."""
    # Create project directories
    projects = [
        {
            "name": "00.project1",
            "readme": """---
author: Author1
project_name: Project 1
project_source: https://github.com/test/project1
stable_images:
  - image1:1.0.0
date: 2026-04-23
last_updated: 2026-04-23
supported_architecture:
  - amd64
ready_to_deploy: true
---
# Project 1""",
        },
        {
            "name": "01.project2",
            "readme": """---
author: Author2
project_name: Project 2
project_source: https://github.com/test/project2
stable_images:
  - image2:2.0.0
date: 2026-04-22
last_updated: 2026-04-22
supported_architecture:
  - arm64
ready_to_deploy: false
---
# Project 2""",
        },
    ]

    for project in projects:
        project_dir = tmp_path / project["name"]
        project_dir.mkdir()
        readme_file = project_dir / "readme.md"
        readme_file.write_text(project["readme"])

    # Create API structure
    api_dir = tmp_path / "00.api" / "v1"
    api_dir.mkdir(parents=True, exist_ok=True)

    yield tmp_path
