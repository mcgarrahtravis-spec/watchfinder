from __future__ import annotations

import abc
import statistics
from typing import Iterable

from watchfinder.models import AuctionLot, CompSale, MarketComps


class CompProvider(abc.ABC):
    name: str

    @abc.abstractmethod
    def lookup(self, query: str, lot: AuctionLot | None = None) -> list[CompSale]:
        raise NotImplementedError


def summarize_comps(
    query: str,
    comps: list[CompSale],
    brand: str | None = None,
    model: str | None = None,
    reference: str | None = None,
    notes: str | None = None,
) -> MarketComps | None:
    prices = [c.price for c in comps if c.price and c.price > 0]
    if not prices:
        return None
    prices_sorted = sorted(prices)
    return MarketComps(
        query=query,
        brand=brand,
        model=model,
        reference=reference,
        comps=comps,
        median_price=float(statistics.median(prices_sorted)),
        low_price=float(prices_sorted[0]),
        high_price=float(prices_sorted[-1]),
        sample_size=len(prices_sorted),
        notes=notes,
    )


def merge_comp_lists(groups: Iterable[list[CompSale]], limit: int = 12) -> list[CompSale]:
    merged: list[CompSale] = []
    seen: set[str] = set()
    for group in groups:
        for comp in group:
            key = f"{comp.source.value}:{comp.title}:{comp.price}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(comp)
            if len(merged) >= limit:
                return merged
    return merged