from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from watchfinder.comps.base import CompProvider
from watchfinder.models import AuctionLot, CompSale, CompSource


PRICE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{2})?)")


class EbaySoldProvider(CompProvider):
    """Best-effort eBay sold/completed comps.

    eBay commonly blocks datacenter IPs. When blocked, this returns [].
    Prefer official APIs or residential egress for production use.
    """

    name = "ebay"

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
            "https://www.ebay.com/sch/i.html?"
            f"_nkw={quote_plus(query)}&LH_Sold=1&LH_Complete=1&rt=nc&_ipg=25"
        )
        try:
            resp = cffi_requests.get(url, impersonate="chrome131", timeout=40)
        except Exception:
            return []
        if resp.status_code != 200 or "Error Page" in resp.text[:500]:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        comps: list[CompSale] = []
        items = soup.select(".s-item")
        for item in items:
            title_el = item.select_one(".s-item__title")
            price_el = item.select_one(".s-item__price")
            link_el = item.select_one("a.s-item__link")
            if not title_el or not price_el:
                continue
            title = title_el.get_text(" ", strip=True)
            if not title or title.lower().startswith("shop on ebay"):
                continue
            price_text = price_el.get_text(" ", strip=True)
            match = PRICE_RE.search(price_text)
            if not match:
                continue
            price = float(match.group(1).replace(",", ""))
            href = link_el.get("href") if link_el else None
            comps.append(
                CompSale(
                    source=CompSource.EBAY,
                    title=title,
                    price=price,
                    url=href,
                    is_asking_price=False,
                )
            )
            if len(comps) >= self.max_comps:
                break
        return comps