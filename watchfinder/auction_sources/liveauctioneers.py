from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from watchfinder.auction_sources.base import AuctionSource
from watchfinder.models import AuctionLot, SourceName
from watchfinder.parser import is_likely_watch, parse_watch_title


class LiveAuctioneersSource(AuctionSource):
    """Best-effort LiveAuctioneers search.

    LiveAuctioneers is frequently behind Imperva bot protection. This adapter
    tries public search pages and returns an empty list (with a raised error
    callers can catch) when blocked.
    """

    name = "liveauctioneers"

    def search(self, query: str) -> list[AuctionLot]:
        self._throttle()
        url = (
            "https://www.liveauctioneers.com/search/"
            f"?keyword={quote_plus(query)}&categoryIds=101"
        )
        resp = cffi_requests.get(url, impersonate="chrome131", timeout=45)
        if resp.status_code != 200 or len(resp.text) < 2000:
            raise RuntimeError(
                "LiveAuctioneers blocked or unavailable from this network "
                "(bot protection). Import lots via CSV or retry from a residential IP."
            )
        soup = BeautifulSoup(resp.text, "html.parser")
        # Prefer embedded JSON state when present
        lots = self._from_next_data(soup, query) or self._from_anchors(soup, query)
        return lots[: self.max_lots]

    def _from_next_data(self, soup: BeautifulSoup, query: str) -> list[AuctionLot]:
        for script in soup.find_all("script"):
            text = script.string or ""
            if "itemId" in text and "estimate" in text.lower():
                # Very loose extraction — structure changes often
                try:
                    match = re.search(r"\{.*\"items\".*\}", text, re.S)
                    if not match:
                        continue
                    payload = json.loads(match.group(0))
                except Exception:
                    continue
                return []
        return []

    def _from_anchors(self, soup: BeautifulSoup, query: str) -> list[AuctionLot]:
        lots: list[AuctionLot] = []
        for a in soup.select("a[href*='/item/']"):
            href = a.get("href") or ""
            title = a.get_text(" ", strip=True)
            if not title or not is_likely_watch(title):
                continue
            parsed = parse_watch_title(title, fallback_query=query)
            m = re.search(r"/item/(\d+)", href)
            if not m:
                continue
            item_id = m.group(1)
            url = href if href.startswith("http") else f"https://www.liveauctioneers.com{href}"
            lots.append(
                AuctionLot(
                    source=SourceName.LIVEAUCTIONEERS,
                    source_id=item_id,
                    title=title,
                    url=url,
                    brand=parsed.brand,
                    model=parsed.model,
                    reference=parsed.reference,
                    search_query=query,
                    auction_house="LiveAuctioneers",
                )
            )
        return lots