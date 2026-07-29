from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    application_name: str = "Continuity"
    application_version: str = "0.1.0"
    environment: str = "development"

    public_base_url: str = "http://localhost:8000"

    heartbeat_scheduler_enabled: bool = False
    heartbeat_scheduler_interval_seconds: int = 300
    heartbeat_pending_alert_seconds: int = Field(default=3_600, gt=0)

    lifecycle_day_seconds: int = Field(default=86_400, gt=0)

    dashboard_display_timezone: str = "Europe/London"

    database_host: str = "postgres"
    database_port: int = 5432
    database_name: str = "continuity"
    database_user: str = "continuity"
    database_password: str | None = None
    database_password_file: Path | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CONTINUITY_",
        extra="ignore",
    )

    def get_database_password(self) -> str:
        if self.database_password:
            return self.database_password

        if self.database_password_file:
            return self.database_password_file.read_text(encoding="utf-8").strip()

        raise RuntimeError(
            "Database password is not configured. Set "
            "CONTINUITY_DATABASE_PASSWORD or "
            "CONTINUITY_DATABASE_PASSWORD_FILE."
        )

    @property
    def effective_lifecycle_day_seconds(self) -> int:
        """Return accelerated lifecycle timing outside production only."""
        if self.environment.strip().lower() == "production":
            return 86_400

        return self.lifecycle_day_seconds

    @property
    def database_url(self) -> str:
        password = self.get_database_password()

        return (
            f"postgresql+psycopg://{self.database_user}:{password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )


settings = Settings()
