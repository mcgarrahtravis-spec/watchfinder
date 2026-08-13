from watchfinder.config import AppConfig
from watchfinder.pipeline import run_scan
from watchfinder.auction_sources.csv_import import CsvImportSource
from pathlib import Path


def test_demo_csv_scan(tmp_path: Path, monkeypatch):
    demo = Path(__file__).resolve().parents[1] / "data" / "demo_lots.json"
    cfg = AppConfig()
    cfg.sources.hibid = False
    cfg.sources.catawiki = False
    cfg.sources.liveauctioneers = False
    cfg.sources.csv_path = str(demo)
    cfg.comps.use_ebay = False
    cfg.comps.use_chrono24 = False
    cfg.comps.use_reference = True
    cfg.queries = ["Rolex", "Omega", "Seiko"]

    result = run_scan(cfg)
    assert len(result.lots) >= 2
    assert any(d.verdict == "worth_a_look" for d in result.deals)
    assert result.meta.get("dropped_outside_window", 0) >= 1
    assert result.meta.get("dropped_stock_photos", 0) >= 1