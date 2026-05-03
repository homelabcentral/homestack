"""Tests for readme front matter Pydantic models."""

from datetime import date

import pytest
from models import ConfigFile, ReadmeFrontMatter, Step
from pydantic import ValidationError


class TestConfigFile:
    """Test cases for ConfigFile model."""

    def test_config_file_valid(self):
        """Test creating a valid ConfigFile."""
        config = ConfigFile(path="config.yml", constant=True, keys={"key1": "value1"})
        assert config.path == "config.yml"
        assert config.constant is True
        assert config.keys == {"key1": "value1"}

    def test_config_file_minimal(self):
        """Test ConfigFile with minimal required fields."""
        config = ConfigFile(path="config.yml", constant=False)
        assert config.path == "config.yml"
        assert config.constant is False
        assert config.keys is None

    def test_config_file_missing_path(self):
        """Test ConfigFile validation fails without path."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigFile(constant=True)
        assert "path" in str(exc_info.value)

    def test_config_file_missing_constant(self):
        """Test ConfigFile validation fails without constant."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigFile(path="config.yml")
        assert "constant" in str(exc_info.value)


class TestStep:
    """Test cases for Step model."""

    def test_step_valid(self):
        """Test creating a valid Step."""
        step = Step(
            number=1, description="Install dependencies", todo="apt-get install -y"
        )
        assert step.number == 1
        assert step.description == "Install dependencies"
        assert step.todo == "apt-get install -y"

    def test_step_missing_fields(self):
        """Test Step validation fails with missing fields."""
        with pytest.raises(ValidationError):
            Step(number=1)

    def test_step_invalid_number_type(self):
        """Test Step validation fails with invalid number type."""
        with pytest.raises(ValidationError):
            Step(number="one", description="Test", todo="test")


class TestReadmeFrontMatter:
    """Test cases for ReadmeFrontMatter model."""

    def test_required_fields_only(self):
        """Test creating ReadmeFrontMatter with only required fields."""
        front_matter = ReadmeFrontMatter(
            author="Test Author",
            project_name="Test Project",
            project_source="https://github.com/test/project",
            stable_images=["image:1.0.0"],
            date="2026-04-23",
            last_updated="2026-04-23",
            supported_architecture=["amd64"],
            ready_to_deploy=True,
        )
        assert front_matter.author == "Test Author"
        assert front_matter.project_name == "Test Project"
        assert front_matter.ready_to_deploy is True

    def test_all_fields(self):
        """Test creating ReadmeFrontMatter with all fields."""
        front_matter = ReadmeFrontMatter(
            author="Test Author",
            project_name="Test Project",
            project_source="https://github.com/test/project",
            stable_images=["image:1.0.0"],
            date="2026-04-23",
            last_updated="2026-04-23",
            supported_architecture=["amd64"],
            ready_to_deploy=True,
            project_description="Description",
            project_website="https://example.com",
            project_docs="https://docs.example.com",
            project_status="Active",
            stable_versions=["1.0.0"],
            latest_images=["image:latest"],
            latest_versions=["2.0.0"],
            warning="Test warning",
            required_env_files=["test.env"],
            config_files=[{"path": "config.yml", "constant": True}],
            pre_install_steps=[Step(number=1, description="Pre-install", todo="setup")],
            post_install_steps=[
                Step(number=1, description="Post-install", todo="configure")
            ],
            post_setup_steps=[
                Step(number=1, description="Post-setup", todo="finalize")
            ],
        )
        assert front_matter.project_description == "Description"
        assert front_matter.project_status == "Active"
        assert len(front_matter.pre_install_steps) == 1

    def test_optional_fields_none(self):
        """Test that optional fields default to None."""
        front_matter = ReadmeFrontMatter(
            author="Test Author",
            project_name="Test Project",
            project_source="https://github.com/test/project",
            stable_images=["image:1.0.0"],
            date="2026-04-23",
            last_updated="2026-04-23",
            supported_architecture=["amd64"],
            ready_to_deploy=True,
        )
        assert front_matter.project_description is None
        assert front_matter.project_website is None
        assert front_matter.warning is None
        assert front_matter.pre_install_steps is None

    def test_missing_required_field(self):
        """Test validation fails when required field is missing."""
        with pytest.raises(ValidationError) as exc_info:
            ReadmeFrontMatter(
                project_name="Test Project",
                project_source="https://github.com/test/project",
                stable_images=["image:1.0.0"],
                date="2026-04-23",
                last_updated="2026-04-23",
                supported_architecture=["amd64"],
                ready_to_deploy=True,
            )
        assert "author" in str(exc_info.value)

    def test_model_dump_exclude_none(self):
        """Test model_dump excludes None values."""
        front_matter = ReadmeFrontMatter(
            author="Test Author",
            project_name="Test Project",
            project_source="https://github.com/test/project",
            stable_images=["image:1.0.0"],
            date="2026-04-23",
            last_updated="2026-04-23",
            supported_architecture=["amd64"],
            ready_to_deploy=True,
            project_status="Active",
        )
        data = front_matter.model_dump(exclude_none=True)
        assert "author" in data
        assert "project_status" in data
        assert "project_description" not in data
        assert "project_website" not in data

    def test_date_field_conversion(self):
        """Test that date fields are stored as strings."""
        front_matter = ReadmeFrontMatter(
            author="Test Author",
            project_name="Test Project",
            project_source="https://github.com/test/project",
            stable_images=["image:1.0.0"],
            date="2026-04-23",
            last_updated="2026-04-23",
            supported_architecture=["amd64"],
            ready_to_deploy=True,
        )
        assert isinstance(front_matter.date, str)
        assert isinstance(front_matter.last_updated, str)
        assert front_matter.date == "2026-04-23"

    def test_date_field_conversion_from_date_objects(self):
        """Test that datetime.date inputs are converted to ISO strings."""
        front_matter = ReadmeFrontMatter(
            author="Test Author",
            project_name="Test Project",
            project_source="https://github.com/test/project",
            stable_images=["image:1.0.0"],
            date=date(2026, 4, 23),
            last_updated=date(2026, 4, 24),
            supported_architecture=["amd64"],
            ready_to_deploy=True,
        )
        assert front_matter.date == "2026-04-23"
        assert front_matter.last_updated == "2026-04-24"

    def test_date_validator_uses_non_shadowed_type_annotation(self):
        """Test regression: validator annotation should not use shadowed field name."""
        annotation = ReadmeFrontMatter.convert_date_to_string.__annotations__["v"]
        assert "FieldInfo" not in repr(annotation)
        assert "DateType" in ReadmeFrontMatter.convert_date_to_string.__code__.co_names

    def test_validate_assignment_enabled(self):
        """Test that validate_assignment is enabled."""
        front_matter = ReadmeFrontMatter(
            author="Test Author",
            project_name="Test Project",
            project_source="https://github.com/test/project",
            stable_images=["image:1.0.0"],
            date="2026-04-23",
            last_updated="2026-04-23",
            supported_architecture=["amd64"],
            ready_to_deploy=True,
        )
        # Should validate on assignment
        front_matter.project_name = "New Name"
        assert front_matter.project_name == "New Name"

    def test_list_fields_not_empty(self):
        """Test that list fields can accept empty lists (Pydantic allows this)."""
        # Note: Pydantic allows empty lists; validation would require min_length constraint
        front_matter = ReadmeFrontMatter(
            author="Test Author",
            project_name="Test Project",
            project_source="https://github.com/test/project",
            stable_images=[],
            date="2026-04-23",
            last_updated="2026-04-23",
            supported_architecture=[],
            ready_to_deploy=True,
        )
        assert front_matter.stable_images == []
        assert front_matter.supported_architecture == []
