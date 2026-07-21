from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    application_name: str = "Digital Continuity"
    application_version: str = "0.1.0"
    environment: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CONTINUITY_",
        extra="ignore",
    )


settings = Settings()
