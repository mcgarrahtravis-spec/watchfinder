from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from watchfinder.auction_sources.base import AuctionSource
from watchfinder.models import AuctionLot, SourceName
from watchfinder.parser import parse_watch_title


class CsvImportSource(AuctionSource):
    """Import auction lots from a local CSV or JSON file.

    CSV columns (flexible): title, url, current_bid, currency, source,
    source_id, bid_count, location, auction_house, image_url, ends_at
    """

    name = "csv"

    def __init__(self, path: str | Path, **kwargs: Any):
        super().__init__(**kwargs)
        self.path = Path(path)

    def search(self, query: str) -> list[AuctionLot]:
        # CSV source ignores query filtering beyond simple substring match
        lots = self._load_all()
        q = query.lower()
        matched = [lot for lot in lots if q in lot.title.lower() or not query]
        return matched[: self.max_lots]

    def search_many(self, queries):  # type: ignore[override]
        lots = self._load_all()
        if not queries:
            return lots[: self.max_lots]
        out: list[AuctionLot] = []
        seen: set[str] = set()
        for lot in lots:
            key = f"{lot.source.value}:{lot.source_id}"
            if key in seen:
                continue
            title_l = lot.title.lower()
            matched = False
            for q in queries:
                tokens = [t for t in q.lower().split() if t]
                if tokens and all(t in title_l for t in tokens):
                    matched = True
                    break
                if q.lower() in title_l:
                    matched = True
                    break
            if matched:
                seen.add(key)
                out.append(lot)
        return out[: self.max_lots]

    def _load_all(self) -> list[AuctionLot]:
        if not self.path.exists():
            raise FileNotFoundError(f"Import file not found: {self.path}")
        if self.path.suffix.lower() == ".json":
            return self._from_json(self.path)
        return self._from_csv(self.path)

    def _from_json(self, path: Path) -> list[AuctionLot]:
        data = json.loads(path.read_text())
        rows = data if isinstance(data, list) else data.get("lots", [])
        return [self._row_to_lot(row) for row in rows]

    def _from_csv(self, path: Path) -> list[AuctionLot]:
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            return [self._row_to_lot(row) for row in reader]

    def _row_to_lot(self, row: dict[str, Any]) -> AuctionLot:
        from datetime import datetime, timezone

        title = str(row.get("title") or "").strip()
        parsed = parse_watch_title(title)
        source_raw = str(row.get("source") or "csv").lower()
        try:
            source = SourceName(source_raw)
        except ValueError:
            source = SourceName.CSV
        current = row.get("current_bid")
        ends_at = None
        raw_end = row.get("ends_at")
        if raw_end:
            try:
                ends_at = datetime.fromisoformat(str(raw_end).replace("Z", "+00:00"))
                if ends_at.tzinfo is None:
                    ends_at = ends_at.replace(tzinfo=timezone.utc)
            except ValueError:
                ends_at = None
        return AuctionLot(
            source=source if source != SourceName.CSV else SourceName.CSV,
            source_id=str(row.get("source_id") or row.get("id") or title[:40]),
            title=title,
            url=str(row.get("url") or ""),
            current_bid=float(current) if current not in (None, "") else None,
            currency=str(row.get("currency") or "USD"),
            bid_count=int(row["bid_count"]) if row.get("bid_count") not in (None, "") else None,
            ends_at=ends_at,
            time_left=row.get("time_left"),
            location=row.get("location"),
            auction_house=row.get("auction_house"),
            image_url=row.get("image_url"),
            brand=parsed.brand,
            model=parsed.model,
            reference=parsed.reference,
            search_query=parsed.query,
            raw=dict(row),
        )