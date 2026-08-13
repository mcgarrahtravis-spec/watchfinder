from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from watchfinder.auction_sources import (
    CatawikiSource,
    CsvImportSource,
    HiBidSource,
    LiveAuctioneersSource,
)
from watchfinder.comps import (
    Chrono24Provider,
    EbaySoldProvider,
    ReferenceCompProvider,
    merge_comp_lists,
    summarize_comps,
)
from watchfinder.config import AppConfig
from watchfinder.filters import FilterConfig, filter_lots
from watchfinder.models import AuctionLot, DealOpportunity, ScanResult
from watchfinder.parser import parse_watch_title
from watchfinder.scoring import score_deal


def build_sources(cfg: AppConfig) -> list[Any]:
    sources: list[Any] = []
    common = {
        "rate_limit_seconds": cfg.rate_limit_seconds,
        "max_lots": cfg.max_lots_per_source,
    }
    if cfg.sources.hibid:
        sources.append(HiBidSource(**common))
    if cfg.sources.catawiki:
        sources.append(
            CatawikiSource(currency=cfg.deal.currency, **common)
        )
    if cfg.sources.liveauctioneers:
        sources.append(LiveAuctioneersSource(**common))
    if cfg.sources.csv_path:
        sources.append(CsvImportSource(cfg.sources.csv_path, **common))
    return sources


def build_comp_providers(cfg: AppConfig) -> list[Any]:
    providers: list[Any] = []
    if cfg.comps.use_ebay:
        providers.append(EbaySoldProvider(max_comps=cfg.comps.max_comps_per_query))
    if cfg.comps.use_chrono24:
        providers.append(Chrono24Provider(max_comps=cfg.comps.max_comps_per_query))
    if cfg.comps.use_reference:
        providers.append(ReferenceCompProvider())
    return providers


def enrich_lot(lot: AuctionLot) -> AuctionLot:
    if lot.brand and lot.model:
        return lot
    parsed = parse_watch_title(lot.title, fallback_query=lot.search_query)
    lot.brand = lot.brand or parsed.brand
    lot.model = lot.model or parsed.model
    lot.reference = lot.reference or parsed.reference
    return lot


def comps_for_lot(lot: AuctionLot, providers: list[Any], cfg: AppConfig):
    query = " ".join(
        p for p in (lot.brand, lot.model, lot.reference) if p
    ) or lot.search_query or lot.title
    groups = []
    notes_parts = []
    for provider in providers:
        try:
            found = provider.lookup(query, lot=lot)
        except Exception as exc:  # noqa: BLE001
            notes_parts.append(f"{provider.name} error: {exc}")
            found = []
        if found:
            groups.append(found)
            notes_parts.append(f"{provider.name}:{len(found)}")
        elif provider.name in {"ebay", "chrono24"}:
            notes_parts.append(f"{provider.name}:blocked_or_empty")
    merged = merge_comp_lists(groups, limit=cfg.comps.max_comps_per_query)
    return summarize_comps(
        query=query,
        comps=merged,
        brand=lot.brand,
        model=lot.model,
        reference=lot.reference,
        notes="; ".join(notes_parts) if notes_parts else None,
    )


def run_scan(cfg: AppConfig | None = None, queries: list[str] | None = None) -> ScanResult:
    cfg = cfg or AppConfig()
    queries = queries or cfg.queries
    sources = build_sources(cfg)
    providers = build_comp_providers(cfg)

    lots: list[AuctionLot] = []
    errors: list[str] = []
    meta: dict[str, Any] = {"sources": [s.name for s in sources]}

    for source in sources:
        try:
            found = source.search_many(queries)
            lots.extend(found)
            meta[f"{source.name}_count"] = len(found)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source.name}: {exc}")

    lots = [enrich_lot(lot) for lot in lots]
    raw_count = len(lots)

    filter_cfg = FilterConfig(**cfg.filters.model_dump())
    lots, filter_notes, filter_meta = filter_lots(lots, filter_cfg)
    meta.update(filter_meta)
    meta["raw_lot_count"] = raw_count
    # Keep filter notes short in the UI — summarize plus a few examples.
    if filter_notes:
        summary = (
            f"Filters removed {raw_count - len(lots)} lots "
            f"(outside {cfg.filters.max_hours_until_end:.0f}h window: "
            f"{filter_meta['dropped_outside_window']}, "
            f"stock/catalog photos: {filter_meta['dropped_stock_photos']})"
        )
        errors.append(summary)
        errors.extend(filter_notes[:8])

    # Cache comps by query key to avoid hammering providers
    comps_cache: dict[str, Any] = {}
    deals: list[DealOpportunity] = []
    for lot in lots:
        key = " ".join(p for p in (lot.brand, lot.model, lot.reference) if p) or lot.title
        if key not in comps_cache:
            comps_cache[key] = comps_for_lot(lot, providers, cfg)
        deal = score_deal(lot, comps_cache[key], cfg.deal)
        deals.append(deal)

    deals.sort(key=lambda d: (d.verdict != "worth_a_look", -d.score, d.all_in_cost or 0))

    return ScanResult(
        scanned_at=datetime.now(timezone.utc),
        queries=list(queries),
        lots=lots,
        deals=deals,
        errors=errors,
        meta=meta,
    )