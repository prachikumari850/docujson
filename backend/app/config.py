import secrets
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    app_name: str = "DocuJSON"
    storage_dir: str = "../storage"
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "neetday"
    max_upload_mb: int = Field(default=50, gt=0)

    session_expire_hours: int = Field(default=24, gt=0, le=720)
    cookie_secure: bool = False
    cookie_same_site: Literal["lax", "strict", "none"] = "lax"
    password_reset_expire_minutes: int = Field(default=30, gt=0, le=1440)
    csrf_secret: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        min_length=32,
    )

    ollama_enabled: bool = False
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5vl:3b"
    ollama_timeout_seconds: float = Field(default=90.0, gt=0)

    tesseract_cmd: str | None = None
    tessdata_prefix: str | None = None
    ocr_languages: str = Field(
        default="eng+hin",
        validation_alias=AliasChoices("OCR_LANGUAGES", "TESSERACT_LANG"),
    )
    ocr_dpi: int = Field(default=300, ge=72, le=600)
    media_crop_margin_pt: float = Field(default=6.0, ge=0, le=72)
    math_crop_dpi: int = Field(default=288, ge=72, le=600)

    cors_origins: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def storage_path(self) -> Path:
        path = Path(self.storage_dir)

        if not path.is_absolute():
            path = (BASE_DIR / path).resolve()

        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
