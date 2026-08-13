from datetime import datetime, timedelta, timezone

from watchfinder.filters import FilterConfig, ends_within_horizon, filter_lots, score_stock_photo
from watchfinder.models import AuctionLot, SourceName


def _lot(**kwargs) -> AuctionLot:
    defaults = dict(
        source=SourceName.HIBID,
        source_id="1",
        title="Rolex Submariner",
        url="https://example.com",
    )
    defaults.update(kwargs)
    return AuctionLot(**defaults)


def test_ends_within_24h_keeps_near_lots():
    now = datetime(2026, 8, 13, 16, 0, tzinfo=timezone.utc)
    cfg = FilterConfig(max_hours_until_end=24, require_end_time=True, reject_stock_photos=False)
    keep = _lot(ends_at=now + timedelta(hours=6))
    drop = _lot(source_id="2", ends_at=now + timedelta(hours=30))
    missing = _lot(source_id="3", ends_at=None)
    assert ends_within_horizon(keep, cfg, now=now).keep
    assert not ends_within_horizon(drop, cfg, now=now).keep
    assert not ends_within_horizon(missing, cfg, now=now).keep


def test_stock_text_rejected():
    lot = _lot(title="Rolex Submariner STOCK PHOTO only")
    score, reasons = score_stock_photo(lot)
    assert score >= 4
    assert any("stock" in r.lower() for r in reasons)


def test_synthetic_stock_image_rejected_on_hibid():
    lot = _lot(
        source=SourceName.HIBID,
        image_url="/static/demo/stock_like.jpg",
        title="Rolex Submariner Date",
    )
    cfg = FilterConfig(reject_stock_photos=True, require_end_time=False)
    kept, notes, meta = filter_lots(
        [lot],
        cfg,
        now=datetime.now(timezone.utc),
    )
    assert kept == []
    assert meta["dropped_stock_photos"] == 1


def test_filter_lots_combines_rules():
    now = datetime(2026, 8, 13, 16, 0, tzinfo=timezone.utc)
    ok = _lot(
        source_id="ok",
        ends_at=now + timedelta(hours=3),
        image_url="/static/demo/hibid_0.jpg",
        title="Rolex Submariner 14060",
    )
    far = _lot(
        source_id="far",
        ends_at=now + timedelta(hours=40),
        image_url="/static/demo/hibid_0.jpg",
        title="Rolex Submariner 14060 far",
    )
    stock = _lot(
        source_id="stock",
        ends_at=now + timedelta(hours=2),
        image_url="/static/demo/stock_like.jpg",
        title="Rolex Submariner catalog",
    )
    cfg = FilterConfig(max_hours_until_end=24, reject_stock_photos=True)
    kept, notes, meta = filter_lots([ok, far, stock], cfg, now=now)
    assert [lot.source_id for lot in kept] == ["ok"]
    assert meta["dropped_outside_window"] == 1
    assert meta["dropped_stock_photos"] == 1
