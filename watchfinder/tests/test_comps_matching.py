from watchfinder.comps.reference import ReferenceCompProvider, _load_reference
from watchfinder.models import AuctionLot, SourceName
from watchfinder.parser import parse_watch_title


def test_seiko_chronographs_do_not_get_skx_comps():
    _load_reference.cache_clear()
    provider = ReferenceCompProvider()
    titles = [
        "Seiko - SND371P1 - No reserve price - Chronograph Watch Men Quartz",
        "Seiko - Chronograph - No reserve price - SBTR015 - Men - Quartz",
        "Seiko - Chronograph Green Dial - No reserve price - 8T63 - Men",
    ]
    prices = []
    for title in titles:
        parsed = parse_watch_title(title)
        lot = AuctionLot(
            source=SourceName.CATAWIKI,
            source_id="x",
            title=title,
            url="https://example.com",
            brand=parsed.brand,
            model=parsed.model,
            reference=parsed.reference,
        )
        comps = provider.lookup(parsed.query or title, lot=lot)
        assert comps, f"expected comps for {title} parsed={parsed}"
        median = comps[1].price
        prices.append(median)
        # Must not be the SKX $280 bucket
        assert median != 280, f"{title} incorrectly used SKX comps"
        assert "skx" not in comps[1].title.lower()
    # At least some differentiation across refs
    assert len(set(prices)) >= 2


def test_brand_only_seiko_returns_no_comps():
    _load_reference.cache_clear()
    provider = ReferenceCompProvider()
    lot = AuctionLot(
        source=SourceName.CATAWIKI,
        source_id="y",
        title="Seiko Watch",
        url="https://example.com",
        brand="Seiko",
        model=None,
        reference=None,
    )
    assert provider.lookup("Seiko", lot=lot) == []


def test_parse_seiko_chrono_refs():
    p1 = parse_watch_title("Seiko - SND371P1 - Chronograph Watch")
    assert p1.brand == "Seiko"
    assert p1.reference and p1.reference.startswith("SND371")
    assert p1.model == "Chronograph"

    p2 = parse_watch_title("Seiko SBTR015 Chronograph")
    assert p2.reference and "SBTR015" in p2.reference

    p3 = parse_watch_title("Seiko Chronograph Green Dial 100m 8T63")
    assert p3.reference == "8T63"
