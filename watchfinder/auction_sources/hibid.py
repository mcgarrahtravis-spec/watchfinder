from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import httpx

from watchfinder.auction_sources.base import AuctionSource
from watchfinder.models import AuctionLot, SourceName
from watchfinder.parser import is_likely_watch, parse_watch_title


LOT_SEARCH_QUERY = """
query LotSearch($input: LotSearchInput!) {
  lotSearch(input: $input) {
    pagedResults {
      pageNumber
      totalCount
      results {
        id
        itemId
        lotNumber
        lead
        bidAmount
        estimate
        shippingOffered
        distanceMiles
        auctioneer { id name }
        auction {
          id
          eventName
          eventCity
          eventZip
          eventState
          eventDateEnd
          lotCount
        }
        lotState {
          bidCount
          highBid
          timeLeft
          timeLeftSeconds
          status
          buyNow
          biddingExtended
        }
        pictures {
          thumbnailLocation
          fullSizeLocation
        }
      }
    }
  }
}
"""


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:80] or "lot"


def _parse_estimate(text: str | None) -> tuple[float | None, float | None]:
    if not text:
        return None, None
    nums = re.findall(r"[\d,]+(?:\.\d+)?", text.replace(",", ""))
    # Above regex after replace commas - fix
    nums = re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))
    if not nums:
        return None, None
    vals = [float(n) for n in nums]
    if len(vals) == 1:
        return vals[0], vals[0]
    return vals[0], vals[1]


class HiBidSource(AuctionSource):
    name = "hibid"
    endpoints = (
        "https://api.hibid.com/graphql",
        "https://hibid.com/graphql",
    )

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://hibid.com",
            "Referer": "https://hibid.com/",
        }

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        # Prefer TLS impersonation — HiBid sits behind Cloudflare.
        try:
            from curl_cffi import requests as cffi_requests

            for endpoint in self.endpoints:
                try:
                    resp = cffi_requests.post(
                        endpoint,
                        json=payload,
                        headers=self._headers,
                        impersonate="chrome131",
                        timeout=45,
                    )
                    if resp.status_code >= 400:
                        last_error = RuntimeError(
                            f"HiBid HTTP {resp.status_code} at {endpoint}"
                        )
                        continue
                    return resp.json()
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
        except ImportError:
            pass

        with httpx.Client(timeout=45.0, headers=self._headers) as client:
            for endpoint in self.endpoints:
                try:
                    resp = client.post(endpoint, json=payload)
                    resp.raise_for_status()
                    return resp.json()
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
        raise RuntimeError(f"HiBid request failed: {last_error}")

    def search(self, query: str) -> list[AuctionLot]:
        self._throttle()
        payload = {
            "query": LOT_SEARCH_QUERY,
            "variables": {
                "input": {
                    "searchText": query,
                    "status": "OPEN",
                    "sortOrder": "TIME_LEFT",
                }
            },
        }
        data = self._post(payload)
        if "errors" in data:
            raise RuntimeError(f"HiBid GraphQL error: {data['errors']}")

        results = (
            data.get("data", {})
            .get("lotSearch", {})
            .get("pagedResults", {})
            .get("results")
            or []
        )
        lots: list[AuctionLot] = []
        for item in results[: self.max_lots]:
            title = (item.get("lead") or "").strip()
            if not title or not is_likely_watch(title):
                continue
            parsed = parse_watch_title(title, fallback_query=query)
            lot_id = str(item["id"])
            state = item.get("lotState") or {}
            auction = item.get("auction") or {}
            auctioneer = item.get("auctioneer") or {}
            pictures = item.get("pictures") or []
            image = None
            if pictures:
                image = pictures[0].get("thumbnailLocation") or pictures[0].get(
                    "fullSizeLocation"
                )
            high_bid = state.get("highBid")
            # HiBid sometimes returns a placeholder in bidAmount; prefer highBid
            current = high_bid if high_bid not in (None, 0) else item.get("bidAmount")
            if current == 123.45:
                current = high_bid or None
            est_low, est_high = _parse_estimate(item.get("estimate"))
            ends_at = None
            time_left = (state.get("timeLeft") or "").strip() or None
            tls = state.get("timeLeftSeconds")
            if isinstance(tls, (int, float)) and tls > 0:
                ends_at = datetime.now(timezone.utc).timestamp() + float(tls)
                ends_at = datetime.fromtimestamp(ends_at, tz=timezone.utc)
            elif auction.get("eventDateEnd"):
                try:
                    ends_at = datetime.fromisoformat(auction["eventDateEnd"]).replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    ends_at = None
            loc_parts = [
                auction.get("eventCity"),
                auction.get("eventState"),
                auction.get("eventZip"),
            ]
            location = ", ".join(p for p in loc_parts if p)
            buy_now = state.get("buyNow") or None
            if buy_now == 0:
                buy_now = None
            lots.append(
                AuctionLot(
                    source=SourceName.HIBID,
                    source_id=lot_id,
                    title=title,
                    url=f"https://hibid.com/lot/{lot_id}/{_slugify(title)}",
                    current_bid=float(current) if current is not None else None,
                    currency="USD",
                    bid_count=state.get("bidCount"),
                    estimate_low=est_low,
                    estimate_high=est_high,
                    buy_now=float(buy_now) if buy_now else None,
                    ends_at=ends_at,
                    time_left=time_left,
                    location=location or None,
                    auction_house=auctioneer.get("name") or auction.get("eventName"),
                    image_url=image,
                    shipping_offered=item.get("shippingOffered"),
                    brand=parsed.brand,
                    model=parsed.model,
                    reference=parsed.reference,
                    search_query=query,
                    raw=item,
                )
            )
        return lots