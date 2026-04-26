from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import DirectoryPath, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CAPTURES_TO_MD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: SecretStr = Field(..., validation_alias="EXTEND_API_KEY")
    watch_dir: DirectoryPath
    supported_extensions: tuple[str, ...] = (
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".docx",
        ".xlsx",
        ".pptx",
    )
    ignore_dirs: tuple[str, ...] = ("assets",)
    workers: int = Field(3, ge=1, le=16)
    stability_seconds: float = 2.0
    stability_poll_interval: float = 0.5
    stability_max_wait_seconds: float = 300.0
    parse_timeout_seconds: float = 1800.0
    history_filename: str = ".ingest_history.json"
    assets_dirname: str = "assets"
    log_level: str = "INFO"
    retry_max_attempts: int = 5
    retry_base_seconds: float = 1.0
    retry_cap_seconds: float = 60.0

    @field_validator("supported_extensions", mode="before")
    @classmethod
    def _normalize_extensions(cls, v: Any) -> Any:
        if v is None:
            return v
        if isinstance(v, str):
            v = [e.strip() for e in v.split(",") if e.strip()]
        out: list[str] = []
        for e in v:
            e = e.lower()
            if not e.startswith("."):
                e = "." + e
            out.append(e)
        return tuple(out)

    @classmethod
    def load(
        cls,
        *,
        watch_dir: Path,
        workers: int | None = None,
        log_level: str | None = None,
        env_file: Path | None = None,
    ) -> "Config":
        overrides: dict[str, Any] = {"watch_dir": watch_dir}
        if workers is not None:
            overrides["workers"] = workers
        if log_level is not None:
            overrides["log_level"] = log_level
        if env_file is not None:
            return cls(_env_file=str(env_file), **overrides)  # type: ignore[call-arg]
        return cls(**overrides)
