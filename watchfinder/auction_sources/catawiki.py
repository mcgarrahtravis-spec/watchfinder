from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from watchfinder.auction_sources.base import AuctionSource
from watchfinder.models import AuctionLot, SourceName
from watchfinder.parser import is_likely_watch, parse_watch_title


class CatawikiSource(AuctionSource):
    name = "catawiki"

    def __init__(self, currency: str = "USD", **kwargs: Any):
        super().__init__(**kwargs)
        self.currency = currency

    def _get(self, url: str) -> cffi_requests.Response:
        self._throttle()
        resp = cffi_requests.get(
            url,
            impersonate="chrome131",
            timeout=45,
            headers={"Accept": "text/html,application/json"},
        )
        resp.raise_for_status()
        return resp

    def _search_lot_cards(self, query: str) -> list[dict[str, Any]]:
        url = (
            f"https://www.catawiki.com/en/s/?q={quote_plus(query)}"
            f"&currency={self.currency}"
        )
        resp = self._get(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        node = soup.find("script", id="__NEXT_DATA__")
        if not node or not node.string:
            return []
        data = json.loads(node.string)
        return (
            data.get("props", {})
            .get("pageProps", {})
            .get("searchLots", {})
            .get("lots")
            or []
        )

    def _current_bid(self, lot_id: int | str) -> tuple[float | None, int | None]:
        url = (
            f"https://www.catawiki.com/buyer/api/v3/lots/{lot_id}/bids"
            f"?currency_code={self.currency}"
        )
        self._throttle()
        resp = cffi_requests.get(url, impersonate="chrome131", timeout=30)
        if resp.status_code != 200:
            return None, None
        payload = resp.json()
        bids = payload.get("bids") or []
        if not bids:
            return None, 0
        top = max(bids, key=lambda b: float(b.get("amount") or 0))
        return float(top["amount"]), len(bids)

    def search(self, query: str) -> list[AuctionLot]:
        cards = self._search_lot_cards(query)
        lots: list[AuctionLot] = []
        for card in cards[: self.max_lots]:
            title = (card.get("title") or "").strip()
            subtitle = (card.get("subtitle") or "").strip()
            full_title = f"{title} — {subtitle}" if subtitle else title
            if not title or not is_likely_watch(full_title):
                continue
            parsed = parse_watch_title(full_title, fallback_query=query)
            lot_id = str(card["id"])
            # Enrich with live bid (rate-limited)
            current_bid, bid_count = self._current_bid(lot_id)
            ends_at = None
            # bidding end isn't always on search card; leave None
            buy_now = None
            if card.get("buyNow") and isinstance(card["buyNow"], dict):
                buy_now = card["buyNow"].get("amount")
            lots.append(
                AuctionLot(
                    source=SourceName.CATAWIKI,
                    source_id=lot_id,
                    title=full_title,
                    url=card.get("url")
                    or f"https://www.catawiki.com/en/l/{lot_id}",
                    current_bid=current_bid,
                    currency=self.currency,
                    bid_count=bid_count,
                    buy_now=float(buy_now) if buy_now else None,
                    ends_at=ends_at,
                    image_url=card.get("thumbImageUrl") or card.get("originalImageUrl"),
                    auction_house="Catawiki",
                    brand=parsed.brand,
                    model=parsed.model,
                    reference=parsed.reference,
                    search_query=query,
                    raw=card,
                )
            )
        return lots