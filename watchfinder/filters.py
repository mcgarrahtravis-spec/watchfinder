"""Lot quality filters: ending soon + stock-photo rejection."""

from __future__ import annotations

import io
import re
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from watchfinder.models import AuctionLot


STOCK_TEXT_RE = re.compile(
    r"(stock\s*photo|stock\s*image|for illustration|illustrative|"
    r"representative\s*photo|photo\s*may\s*not|catalog\s*photo|"
    r"manufacturer\s*photo|image\s*for\s*reference|not\s*actual\s*item|"
    r"stock\s*picture)",
    re.I,
)


@dataclass
class FilterDecision:
    keep: bool
    reasons: list[str]
    stock_score: float = 0.0


@dataclass
class FilterConfig:
    max_hours_until_end: float = 24.0
    require_end_time: bool = True
    reject_stock_photos: bool = True
    # HiBid is riskier with catalog/stock shots — lower bar to reject.
    hibid_stock_threshold: float = 3.0
    other_stock_threshold: float = 5.0
    reject_hibid_without_photo: bool = True


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def ends_within_horizon(lot: AuctionLot, cfg: FilterConfig, now: datetime | None = None) -> FilterDecision:
    now = _aware(now or datetime.now(timezone.utc))
    if lot.ends_at is None:
        if cfg.require_end_time:
            return FilterDecision(False, ["Missing end time — skipped (only showing lots ending within 24h)"])
        return FilterDecision(True, [])
    ends = _aware(lot.ends_at)
    if ends <= now:
        return FilterDecision(False, ["Already ended"])
    horizon = now + timedelta(hours=cfg.max_hours_until_end)
    if ends > horizon:
        hours = (ends - now).total_seconds() / 3600
        return FilterDecision(
            False,
            [f"Ends in {hours:.1f}h — outside {cfg.max_hours_until_end:.0f}h window"],
        )
    return FilterDecision(True, [])


def _load_image_bytes(lot: AuctionLot) -> bytes | None:
    url = lot.image_url
    if not url:
        return None
    # Local static path
    if url.startswith("/static/"):
        path = Path(__file__).resolve().parent / "web" / url.removeprefix("/")
        if path.exists():
            return path.read_bytes()
        # repo-relative fallback
        alt = Path.cwd() / "watchfinder" / "web" / url.removeprefix("/")
        if alt.exists():
            return alt.read_bytes()
        return None
    if url.startswith("http://") or url.startswith("https://"):
        try:
            from curl_cffi import requests as cffi_requests

            resp = cffi_requests.get(url, impersonate="chrome131", timeout=20)
            if resp.status_code == 200 and resp.content:
                ctype = (resp.headers.get("content-type") or "").lower()
                if "image" in ctype or urlparse(url).path.lower().endswith(
                    (".jpg", ".jpeg", ".png", ".webp")
                ):
                    return resp.content
        except Exception:  # noqa: BLE001
            return None
    return None


def _image_stock_features(data: bytes) -> dict[str, float]:
    from PIL import Image

    im = Image.open(io.BytesIO(data)).convert("RGB")
    im = im.resize((160, 160))
    w, h = im.size

    def bright(rgb: tuple[int, int, int]) -> float:
        return sum(rgb) / 3.0

    pixels = [im.getpixel((x, y)) for y in range(h) for x in range(w)]
    white = sum(1 for p in pixels if bright(p) > 240 and max(p) - min(p) < 20) / len(pixels)
    light = sum(1 for p in pixels if bright(p) > 220) / len(pixels)

    bottom = [im.getpixel((x, y)) for y in range(100, 160) for x in range(40, 120)]
    bottom_mid = sum(1 for p in bottom if 40 < bright(p) < 200) / len(bottom)

    corners = []
    for x0, y0 in ((0, 0), (140, 0), (0, 140), (140, 140)):
        patch = [
            bright(im.getpixel((x, y)))
            for y in range(y0, y0 + 20)
            for x in range(x0, x0 + 20)
        ]
        corners.append(sum(patch) / len(patch))
    corner_spread = max(corners) - min(corners)

    edges = 0
    total = 0
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            total += 1
            if abs(bright(im.getpixel((x, y))) - bright(im.getpixel((x + 1, y)))) > 28:
                edges += 1
    edge = edges / total if total else 0.0

    return {
        "white": white,
        "light": light,
        "bottom_mid": bottom_mid,
        "corner_spread": corner_spread,
        "edge": edge,
    }


def score_stock_photo(lot: AuctionLot) -> tuple[float, list[str]]:
    """Return (score, reasons). Higher = more likely stock/catalog photo."""
    score = 0.0
    reasons: list[str] = []

    blob = f"{lot.title} {lot.auction_house or ''} {lot.raw}"
    if STOCK_TEXT_RE.search(blob):
        score += 4.0
        reasons.append("Listing text mentions stock/illustrative photo")

    # Few photos on HiBid luxury lots is a common stock-photo tell.
    pictures = lot.raw.get("pictures") if isinstance(lot.raw, dict) else None
    if lot.source.value == "hibid" and isinstance(pictures, list) and len(pictures) <= 1:
        score += 1.0
        reasons.append("Only one photo on HiBid lot")

    data = _load_image_bytes(lot)
    if not data:
        return score, reasons

    try:
        feats = _image_stock_features(data)
    except Exception:  # noqa: BLE001
        return score, reasons

    if feats["white"] >= 0.75:
        score += 2.0
        reasons.append("Very white studio background")
    elif feats["white"] >= 0.55:
        score += 1.0
        reasons.append("Clean white/catalog background")

    if feats["bottom_mid"] <= 0.12:
        score += 2.0
        reasons.append("Floating product look (little real-world context)")
    elif feats["bottom_mid"] <= 0.35:
        score += 1.0

    if feats["edge"] <= 0.035:
        score += 2.0
        reasons.append("Unusually smooth catalog-like image")
    elif feats["edge"] <= 0.09:
        score += 1.0

    if feats["corner_spread"] <= 0.5 and feats["white"] >= 0.5:
        score += 0.5

    return score, reasons


def stock_photo_decision(lot: AuctionLot, cfg: FilterConfig) -> FilterDecision:
    if not cfg.reject_stock_photos:
        return FilterDecision(True, [])

    score, reasons = score_stock_photo(lot)
    threshold = (
        cfg.hibid_stock_threshold
        if lot.source.value == "hibid"
        else cfg.other_stock_threshold
    )

    if not lot.image_url:
        if lot.source.value == "hibid" and cfg.reject_hibid_without_photo:
            return FilterDecision(
                False,
                ["No photo on HiBid lot — skipped (can't verify against stock images)"],
                stock_score=score,
            )
        return FilterDecision(True, [], stock_score=score)

    # If HiBid image couldn't be analyzed and score is still low, be cautious.
    if (
        lot.source.value == "hibid"
        and score < threshold
        and not _load_image_bytes(lot)
        and cfg.reject_hibid_without_photo
    ):
        return FilterDecision(
            False,
            ["Couldn't analyze HiBid photo — skipped as risky"],
            stock_score=score,
        )

    if score >= threshold:
        detail = "; ".join(reasons) if reasons else "catalog/stock heuristics"
        return FilterDecision(
            False,
            [f"Likely stock/catalog photo (score {score:.1f}): {detail}"],
            stock_score=score,
        )
    return FilterDecision(True, reasons, stock_score=score)


def filter_lots(
    lots: list[AuctionLot],
    cfg: FilterConfig | None = None,
    now: datetime | None = None,
) -> tuple[list[AuctionLot], list[str], dict[str, Any]]:
    cfg = cfg or FilterConfig()
    kept: list[AuctionLot] = []
    notes: list[str] = []
    dropped_end = 0
    dropped_stock = 0

    for lot in lots:
        end_dec = ends_within_horizon(lot, cfg, now=now)
        if not end_dec.keep:
            dropped_end += 1
            notes.append(f"{lot.source.value}:{lot.source_id} — {end_dec.reasons[0]}")
            continue
        stock_dec = stock_photo_decision(lot, cfg)
        if not stock_dec.keep:
            dropped_stock += 1
            notes.append(f"{lot.source.value}:{lot.source_id} — {stock_dec.reasons[0]}")
            continue
        kept.append(lot)

    meta = {
        "filter_max_hours": cfg.max_hours_until_end,
        "dropped_outside_window": dropped_end,
        "dropped_stock_photos": dropped_stock,
        "kept": len(kept),
    }
    return kept, notes, meta
