from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from watchfinder.comps.base import CompProvider
from watchfinder.models import AuctionLot, CompSale, CompSource


DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "reference_prices.json"


@lru_cache(maxsize=1)
def _load_reference() -> list[dict[str, Any]]:
    return json.loads(DATA_PATH.read_text())


class ReferenceCompProvider(CompProvider):
    """Offline secondary-market ranges for popular references.

    Used as a reliable fallback when eBay/Chrono24 scrapes are blocked.
    Numbers are approximate guides — always verify before bidding.
    """

    name = "reference"

    def lookup(self, query: str, lot: AuctionLot | None = None) -> list[CompSale]:
        rows = _load_reference()
        brand = (lot.brand if lot else None) or ""
        model = (lot.model if lot else None) or ""
        reference = (lot.reference if lot else None) or ""
        q = (query or "").lower()

        scored: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            score = 0
            if reference and row.get("reference") and reference.upper() == str(row["reference"]).upper():
                score += 100
            if brand and row.get("brand") and brand.lower() == row["brand"].lower():
                score += 40
            if model and row.get("model") and model.lower() == row["model"].lower():
                score += 40
            rq = (row.get("query") or "").lower()
            if rq and (rq in q or q in rq):
                score += 20
            # Token overlap
            tokens = set(q.split())
            row_tokens = set(rq.split())
            score += 5 * len(tokens & row_tokens)
            if score > 0:
                scored.append((score, row))

        if not scored:
            return []

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best = scored[0]
        if best_score < 40:
            return []

        median = float(best["median_usd"])
        low = float(best.get("low_usd") or median * 0.85)
        high = float(best.get("high_usd") or median * 1.15)
        label = best.get("query") or f"{best.get('brand')} {best.get('model')}"
        note = best.get("notes") or "Reference market range"
        return [
            CompSale(
                source=CompSource.REFERENCE,
                title=f"{label} (ref low)",
                price=low,
                condition=note,
            ),
            CompSale(
                source=CompSource.REFERENCE,
                title=f"{label} (ref median)",
                price=median,
                condition=note,
            ),
            CompSale(
                source=CompSource.REFERENCE,
                title=f"{label} (ref high)",
                price=high,
                condition=note,
            ),
        ]