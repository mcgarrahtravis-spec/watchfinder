from __future__ import annotations

import abc
import time
from typing import Iterable

from watchfinder.models import AuctionLot


class AuctionSource(abc.ABC):
    name: str

    def __init__(self, rate_limit_seconds: float = 1.0, max_lots: int = 40):
        self.rate_limit_seconds = rate_limit_seconds
        self.max_lots = max_lots
        self._last_request = 0.0

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)
        self._last_request = time.time()

    @abc.abstractmethod
    def search(self, query: str) -> list[AuctionLot]:
        raise NotImplementedError

    def search_many(self, queries: Iterable[str]) -> list[AuctionLot]:
        lots: list[AuctionLot] = []
        seen: set[str] = set()
        for query in queries:
            for lot in self.search(query):
                key = f"{lot.source.value}:{lot.source_id}"
                if key in seen:
                    continue
                seen.add(key)
                lots.append(lot)
        return lots