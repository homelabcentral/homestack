"""Application settings loaded from env files using pydantic-settings."""

from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

root_dir = Path(__file__).resolve().parents[3]
project_dir = root_dir / "00.homestack"

app_config_dir = Path(user_config_dir(appname="homestack", appauthor="homelabcentral"))
app_cache_dir = Path(user_cache_dir(appname="homestack", appauthor="homelabcentral"))

prefs_db_path = app_config_dir / "prefs.db"
cache_api_dir = app_cache_dir / "api" / "v1"
log_dir = app_cache_dir / "logs"
log_file = log_dir / "homestack.log"


def _collect_env_files() -> tuple[str, ...]:
    env_dir = root_dir / "00.env"
    return tuple(str(path) for path in sorted(env_dir.glob("*.env")))


class Settings(BaseSettings):
    root_dir: Path = root_dir
    project_dir: Path = project_dir
    app_config_dir: Path = app_config_dir
    app_cache_dir: Path = app_cache_dir
    prefs_db_path: Path = prefs_db_path
    cache_api_dir: Path = cache_api_dir
    log_dir: Path = log_dir
    log_file: Path = log_file

    log_level: str = Field(default="WARNING", alias="HOMESTACK_LOG_LEVEL")

    base_url: str = Field(
        default="https://raw.githubusercontent.com/homelabcentral/homestack/refs/heads/main",
        alias="HOMESTACK_BASE_URL",
    )

    @computed_field
    @property
    def api_url(self) -> str:
        return f"{self.base_url}/00.api/v1"

    model_config = SettingsConfigDict(
        env_file=_collect_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
