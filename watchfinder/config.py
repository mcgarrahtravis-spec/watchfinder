from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class DealConfig(BaseModel):
    min_margin_pct: float = 0.18
    buyer_premium_pct: dict[str, float] = Field(
        default_factory=lambda: {
            "hibid": 0.15,
            "catawiki": 0.12,
            "liveauctioneers": 0.20,
            "csv": 0.15,
            "demo": 0.15,
        }
    )
    estimated_shipping_usd: float = 35.0
    currency: str = "USD"


class CompsConfig(BaseModel):
    use_reference: bool = True
    use_ebay: bool = True
    use_chrono24: bool = True
    max_comps_per_query: int = 8


class SourcesConfig(BaseModel):
    hibid: bool = True
    catawiki: bool = True
    liveauctioneers: bool = False
    csv_path: str | None = None


class AppConfig(BaseModel):
    queries: list[str] = Field(
        default_factory=lambda: [
            "Rolex Submariner",
            "Omega Speedmaster",
            "Tudor Black Bay",
            "Seiko SKX",
        ]
    )
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    comps: CompsConfig = Field(default_factory=CompsConfig)
    deal: DealConfig = Field(default_factory=DealConfig)
    rate_limit_seconds: float = 1.0
    max_lots_per_source: int = 40


class Settings(BaseSettings):
    ebay_app_id: str | None = None
    apify_token: str | None = None

    model_config = {
        "env_prefix": "WATCHFINDER_",
        "env_file": ".env",
        "extra": "ignore",
    }


def load_config(path: str | Path | None = None) -> AppConfig:
    if path is None:
        env_path = os.getenv("WATCHFINDER_CONFIG")
        candidates = []
        if env_path:
            candidates.append(Path(env_path))
        candidates.extend(
            [
                Path("config.yaml"),
                Path("config.demo.yaml"),
                Path("config.example.yaml"),
            ]
        )
        for candidate in candidates:
            if candidate.exists():
                path = candidate
                break
    if path is None:
        return AppConfig()
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text()) or {}
    return AppConfig.model_validate(data)