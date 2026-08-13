from __future__ import annotations

from watchfinder.parser import is_likely_watch, parse_watch_title
from watchfinder.scoring import score_deal
from watchfinder.config import DealConfig
from watchfinder.models import AuctionLot, MarketComps, CompSale, CompSource, SourceName
from watchfinder.comps.reference import ReferenceCompProvider


def test_parse_rolex_submariner():
    parsed = parse_watch_title("Rolex Oyster Perpetual 14060 Submariner")
    assert parsed.brand == "Rolex"
    assert parsed.model == "Submariner"
    assert parsed.reference == "14060"


def test_filters_non_watches():
    assert not is_likely_watch("Omega catalogue 1982 book")
    assert is_likely_watch("Omega Speedmaster Professional Moonwatch")


def test_reference_comps_match():
    provider = ReferenceCompProvider()
    lot = AuctionLot(
        source=SourceName.HIBID,
        source_id="1",
        title="Rolex Submariner 16610",
        url="https://example.com",
        brand="Rolex",
        model="Submariner",
        reference="16610",
    )
    comps = provider.lookup("Rolex Submariner 16610", lot=lot)
    assert len(comps) == 3
    assert comps[1].price == 9500


def test_score_worth_a_look():
    lot = AuctionLot(
        source=SourceName.HIBID,
        source_id="1",
        title="Seiko SKX007",
        url="https://example.com",
        current_bid=100,
        brand="Seiko",
        model="SKX",
        reference="SKX007",
    )
    comps = MarketComps(
        query="Seiko SKX007",
        comps=[CompSale(source=CompSource.REFERENCE, title="x", price=280)],
        median_price=280,
        low_price=180,
        high_price=400,
        sample_size=1,
    )
    deal = score_deal(lot, comps, DealConfig(min_margin_pct=0.18))
    assert deal.verdict == "worth_a_look"
    assert deal.estimated_profit and deal.estimated_profit > 0


def test_score_skip_when_overpriced():
    lot = AuctionLot(
        source=SourceName.CATAWIKI,
        source_id="2",
        title="Rolex Submariner",
        url="https://example.com",
        current_bid=12000,
        brand="Rolex",
        model="Submariner",
    )
    comps = MarketComps(
        query="Rolex Submariner",
        comps=[CompSale(source=CompSource.REFERENCE, title="x", price=10000)],
        median_price=10000,
        sample_size=1,
    )
    deal = score_deal(lot, comps, DealConfig())
    assert deal.verdict == "skip"