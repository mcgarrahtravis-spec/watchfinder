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


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


class ReferenceCompProvider(CompProvider):
    """Offline secondary-market ranges for popular references.

    Matching is intentionally strict: brand alone is never enough, because that
    caused unrelated Seiko chronographs to inherit SKX comps (~$280).
    """

    name = "reference"

    def lookup(self, query: str, lot: AuctionLot | None = None) -> list[CompSale]:
        rows = _load_reference()
        brand = _norm(lot.brand if lot else None)
        model = _norm(lot.model if lot else None)
        reference = _norm(lot.reference if lot else None)
        title = _norm(lot.title if lot else None)
        q = _norm(query)

        # Pull reference-like tokens from the title/query when parser missed them.
        haystack = f"{title} {q}"
        scored: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            row_brand = _norm(row.get("brand"))
            row_model = _norm(row.get("model"))
            row_ref = _norm(row.get("reference"))
            row_query = _norm(row.get("query"))
            score = 0

            if not brand or not row_brand or brand != row_brand:
                continue

            # Exact reference match is strongest.
            if reference and row_ref and reference == row_ref:
                score += 100
            elif row_ref and row_ref in haystack.replace(" ", ""):
                score += 90
            elif row_ref and reference and reference != row_ref:
                # Hard no: known different references must not share comps.
                continue

            # Model family match (Submariner, SKX, Chronograph, etc.).
            if model and row_model and model == row_model:
                score += 50
            elif row_model and row_model in haystack:
                score += 35
            elif model and row_model and model != row_model:
                # Different model families (SKX vs Chronograph) never match.
                continue
            elif row_model and not model and row_model not in haystack:
                # Brand-only lot + specific row model → skip.
                continue

            if row_query and (row_query in haystack or haystack in row_query):
                score += 15

            # Require at least model or reference signal beyond bare brand.
            if score < 35:
                continue
            scored.append((score, row))

        if not scored:
            return []

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best = scored[0]

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
                condition=f"{note} · match score {best_score}",
            ),
            CompSale(
                source=CompSource.REFERENCE,
                title=f"{label} (ref median)",
                price=median,
                condition=f"{note} · match score {best_score}",
            ),
            CompSale(
                source=CompSource.REFERENCE,
                title=f"{label} (ref high)",
                price=high,
                condition=f"{note} · match score {best_score}",
            ),
        ]
