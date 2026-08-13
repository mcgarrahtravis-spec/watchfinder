from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class SourceName(str, Enum):
    HIBID = "hibid"
    CATAWIKI = "catawiki"
    LIVEAUCTIONEERS = "liveauctioneers"
    CSV = "csv"
    DEMO = "demo"


class CompSource(str, Enum):
    REFERENCE = "reference"
    EBAY = "ebay"
    CHRONO24 = "chrono24"
    MANUAL = "manual"


class AuctionLot(BaseModel):
    source: SourceName
    source_id: str
    title: str
    url: str
    current_bid: float | None = None
    currency: str = "USD"
    bid_count: int | None = None
    estimate_low: float | None = None
    estimate_high: float | None = None
    buy_now: float | None = None
    ends_at: datetime | None = None
    time_left: str | None = None
    location: str | None = None
    auction_house: str | None = None
    image_url: str | None = None
    shipping_offered: bool | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    # Parsed identity
    brand: str | None = None
    model: str | None = None
    reference: str | None = None
    search_query: str | None = None


class CompSale(BaseModel):
    source: CompSource
    title: str
    price: float
    currency: str = "USD"
    url: str | None = None
    sold_at: datetime | None = None
    condition: str | None = None
    is_asking_price: bool = False  # Chrono24 listings are asks, not sold


class MarketComps(BaseModel):
    query: str
    brand: str | None = None
    model: str | None = None
    reference: str | None = None
    comps: list[CompSale] = Field(default_factory=list)
    median_price: float | None = None
    low_price: float | None = None
    high_price: float | None = None
    sample_size: int = 0
    notes: str | None = None


class DealOpportunity(BaseModel):
    lot: AuctionLot
    comps: MarketComps | None = None
    all_in_cost: float | None = None
    market_value: float | None = None
    estimated_profit: float | None = None
    margin_pct: float | None = None
    score: float = 0.0
    verdict: str = "skip"
    reasons: list[str] = Field(default_factory=list)


class ScanResult(BaseModel):
    scanned_at: datetime
    queries: list[str]
    lots: list[AuctionLot]
    deals: list[DealOpportunity]
    errors: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)