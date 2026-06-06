"""Configuration loader for plamoindex.

Loads settings from plamoindex.yml with sensible defaults.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class HttpSettings(BaseModel):
    """HTTP client settings."""

    timeout_seconds: float = 30.0
    retry_count: int = 3
    delay_seconds: float = 1.0
    jitter_seconds: float = 0.5
    backoff_base: float = 1.0
    user_agent: str = "plamoindex/0.1 (+https://github.com/plamoindex/plamoindex)"


class SourceSettings(BaseModel):
    """Source plugin settings."""

    enabled: bool = True
    delay_seconds: float = 1.0


class CuratedSettings(BaseModel):
    """Curated data settings."""

    path: str = "curated/"


class OutputSettings(BaseModel):
    """Output/dist settings."""

    dist: str = "dist/"
    compact: bool = True


class RawSettings(BaseModel):
    """Raw collection data settings."""

    path: str = "data/raw/"


class DatasetSettings(BaseModel):
    """Dataset settings."""

    base_url: str = "https://manuals.example.com"


class PlamoIndexConfig(BaseModel):
    """Top-level configuration model."""

    schema_version: int = 1
    http: HttpSettings = Field(default_factory=HttpSettings)
    sources: dict[str, dict[str, Any]] = Field(default_factory=dict)
    curated: CuratedSettings = Field(default_factory=CuratedSettings)
    raw: RawSettings = Field(default_factory=RawSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)
    dataset: DatasetSettings = Field(default_factory=DatasetSettings)


def load_config(path: Path | None = None) -> PlamoIndexConfig:
    """Load plamoindex configuration from a YAML file.

    Falls back to defaults if no path is provided or the file does not exist.

    Args:
        path: Path to plamoindex.yml or None to use defaults.

    Returns:
        PlamoIndexConfig instance.
    """
    if path is None:
        path = Path("plamoindex.yml")

    if not path.is_file():
        return PlamoIndexConfig()

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        return PlamoIndexConfig()

    return PlamoIndexConfig.model_validate(data)
