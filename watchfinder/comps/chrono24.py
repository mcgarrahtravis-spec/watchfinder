from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from watchfinder.comps.base import CompProvider
from watchfinder.models import AuctionLot, CompSale, CompSource


PRICE_RE = re.compile(r"(?:\$|USD)\s*([\d,]+(?:\.\d{2})?)")


class Chrono24Provider(CompProvider):
    """Best-effort Chrono24 asking-price comps (not sold prices).

    Chrono24 is Cloudflare-protected; returns [] when challenged.
    Asking prices usually run above true sold/street prices.
    """

    name = "chrono24"

    def __init__(self, rate_limit_seconds: float = 1.5, max_comps: int = 8):
        self.rate_limit_seconds = rate_limit_seconds
        self.max_comps = max_comps
        self._last = 0.0

    def _throttle(self) -> None:
        elapsed = time.time() - self._last
        if elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)
        self._last = time.time()

    def lookup(self, query: str, lot: AuctionLot | None = None) -> list[CompSale]:
        self._throttle()
        url = (
            "https://www.chrono24.com/search/index.htm?"
            f"query={quote_plus(query)}&dosearch=true"
        )
        try:
            resp = cffi_requests.get(url, impersonate="chrome131", timeout=40)
        except Exception:
            return []
        if resp.status_code != 200 or "cf-mitigated" in resp.text.lower() or len(resp.text) < 5000:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        comps: list[CompSale] = []
        # Chrono24 markup changes; try several selectors
        cards = soup.select("a.article-item-container, div.article-item, a[href*='--id']")
        for card in cards:
            text = card.get_text(" ", strip=True)
            if not text:
                continue
            match = PRICE_RE.search(text)
            if not match:
                continue
            price = float(match.group(1).replace(",", ""))
            href = card.get("href")
            if href and href.startswith("/"):
                href = "https://www.chrono24.com" + href
            title = text[:120]
            comps.append(
                CompSale(
                    source=CompSource.CHRONO24,
                    title=title,
                    price=price,
                    url=href,
                    is_asking_price=True,
                )
            )
            if len(comps) >= self.max_comps:
                break
        return comps