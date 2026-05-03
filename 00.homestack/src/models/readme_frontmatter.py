"""Pydantic models for readme front matter parsing."""

from datetime import date as DateType

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConfigFile(BaseModel):
    """Configuration file metadata.

    Attributes:
        path: File path relative to project root.
        constant: Whether the configuration file is constant/read-only.
        keys: Optional mapping of configuration keys and their types/purposes.
    """

    path: str = Field(..., description="File path relative to project root")
    constant: bool = Field(
        ..., description="Whether the configuration is constant/read-only"
    )
    keys: dict[str, str] | None = Field(
        None, description="Optional mapping of configuration keys"
    )


class Step(BaseModel):
    """Installation, post-installation, or post-setup step.

    Attributes:
        number: Step sequence number.
        description: Human-readable description of the step.
        todo: Command or action to perform.
    """

    number: int = Field(..., description="Step sequence number")
    description: str = Field(..., description="Human-readable description of the step")
    todo: str = Field(..., description="Command or action to perform")


class ReadmeFrontMatter(BaseModel):
    """Parsed front matter from a readme file.

    This model represents the YAML front matter from Docker Compose project readme files.

    Required fields:
        - author: Project author name
        - project_name: Display name of the project
        - project_source: Source repository URL
        - stable_images: List of stable container image references
        - date: Project date
        - last_updated: Last update timestamp
        - supported_architecture: List of supported architectures (e.g., amd64, arm64)
        - ready_to_deploy: Whether the project is ready for deployment

    Optional fields can be None or omitted.
    """

    # Required fields
    author: str = Field(..., description="Project author name")
    project_name: str = Field(..., description="Display name of the project")
    project_source: str = Field(..., description="Source repository URL")
    stable_images: list[str] = Field(
        ..., description="List of stable container image references"
    )
    date: str = Field(..., description="Project date (YYYY-MM-DD format)")
    last_updated: str = Field(
        ..., description="Last update timestamp (YYYY-MM-DD format)"
    )
    supported_architecture: list[str] = Field(
        ..., description="List of supported architectures"
    )
    ready_to_deploy: bool = Field(
        ..., description="Whether the project is ready for deployment"
    )

    # Optional fields
    project_description: str | None = Field(
        None, description="Detailed description of the project"
    )
    project_website: str | None = Field(None, description="Project website URL")
    project_docs: str | None = Field(None, description="Project documentation URL")
    project_status: str | None = Field(
        None, description="Project status (e.g., Active, Archived)"
    )
    stable_versions: list[str] | None = Field(
        None, description="List of stable version strings"
    )
    latest_images: list[str] | None = Field(
        None, description="List of latest container image references"
    )
    latest_versions: list[str] | None = Field(
        None, description="List of latest version strings"
    )
    warning: str | None = Field(None, description="Warning message if any")
    required_env_files: list[str] | None = Field(
        None, description="List of required environment files"
    )
    config_files: list[ConfigFile] | None = Field(
        None, description="List of configuration file mappings"
    )
    pre_install_steps: list[Step] | None = Field(
        None, description="Steps to perform before installation"
    )
    post_install_steps: list[Step] | None = Field(
        None, description="Steps to perform after installation"
    )
    post_setup_steps: list[Step] | None = Field(
        None, description="Steps to perform after setup"
    )

    @field_validator("date", "last_updated", mode="before")
    @classmethod
    def convert_date_to_string(cls, v: DateType | str) -> str:
        """Convert date objects to ISO format strings."""
        if isinstance(v, DateType):
            return v.isoformat()
        return v

    model_config = ConfigDict(validate_assignment=True, use_enum_values=True)
