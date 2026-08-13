"""Extract brand / model / reference hints from auction titles."""

from __future__ import annotations

import re
from dataclasses import dataclass


BRANDS = [
    "Rolex",
    "Omega",
    "Tudor",
    "Cartier",
    "Patek Philippe",
    "Audemars Piguet",
    "Tag Heuer",
    "TAG Heuer",
    "Breitling",
    "IWC",
    "Panerai",
    "Seiko",
    "Grand Seiko",
    "Citizen",
    "Orient",
    "Longines",
    "Hamilton",
    "Tissot",
    "Oris",
    "Zenith",
    "Jaeger-LeCoultre",
    "Vacheron Constantin",
    "Hublot",
    "Richard Mille",
    "Casio",
    "G-Shock",
    "Sinn",
    "Ball",
    "Bulova",
    "Movado",
    "Rado",
    "Nomos",
]

# Common model keywords keyed by brand family
MODELS = [
    "Submariner",
    "Datejust",
    "Daytona",
    "GMT-Master",
    "GMT Master",
    "Explorer",
    "Sea-Dweller",
    "Sea Dweller",
    "Yacht-Master",
    "Yacht Master",
    "Day-Date",
    "Day Date",
    "Oyster Perpetual",
    "Milgauss",
    "Air-King",
    "Speedmaster",
    "Seamaster",
    "Constellation",
    "De Ville",
    "Railmaster",
    "Black Bay",
    "Pelagos",
    "Ranger",
    "Royal Oak",
    "Nautilus",
    "Aquanaut",
    "Santos",
    "Tank",
    "Ballon Bleu",
    "Carrera",
    "Monaco",
    "Navitimer",
    "Superocean",
    "Portugieser",
    "Pilot",
    "Luminor",
    "Radiomir",
    "SKX",
    "Prospex",
    "Presage",
    "Alpinist",
    "Turtle",
    "Samurai",
    "Monster",
    "HydroMod",
    "G-Shock",
    "Casioak",
]

REF_PATTERNS = [
    re.compile(r"\b(\d{4,6}[A-Z]{0,4})\b", re.I),  # 16610, 5513, 14060M
    re.compile(r"\b(\d{3}\.\d{2}\.\d{2}\.\d{2}\.\d{2}\.\d{3})\b"),  # Omega style
    re.compile(r"\b(SKX\d{3})\b", re.I),
    re.compile(r"\b(SRPE\d{2,3})\b", re.I),
    re.compile(r"\b(SPB\d{3})\b", re.I),
]


@dataclass
class ParsedWatch:
    brand: str | None = None
    model: str | None = None
    reference: str | None = None
    query: str | None = None


def _find_brand(title: str) -> str | None:
    lower = title.lower()
    # Longer brands first to prefer Grand Seiko over Seiko, etc.
    for brand in sorted(BRANDS, key=len, reverse=True):
        if brand.lower() in lower:
            return brand.replace("TAG Heuer", "Tag Heuer")
    return None


_GENERIC_MODELS = {
    "oyster perpetual",
    "prospex",
    "presage",
}


def _find_model(title: str) -> str | None:
    lower = title.lower()
    hits = [model for model in MODELS if model.lower() in lower]
    if not hits:
        return None
    # Prefer specific lines (Submariner) over generic family names (Oyster Perpetual)
    specific = [m for m in hits if m.lower() not in _GENERIC_MODELS]
    pool = specific or hits
    return sorted(pool, key=len, reverse=True)[0]


def _find_reference(title: str) -> str | None:
    # Prefer references near known brand/model words
    for pattern in REF_PATTERNS:
        match = pattern.search(title)
        if match:
            ref = match.group(1).upper()
            # Filter out years and tiny numbers
            if ref.isdigit() and (len(ref) == 4 and 1900 <= int(ref) <= 2099):
                continue
            return ref
    return None


def parse_watch_title(title: str, fallback_query: str | None = None) -> ParsedWatch:
    brand = _find_brand(title)
    model = _find_model(title)
    reference = _find_reference(title)

    query_parts = [p for p in (brand, model, reference) if p]
    if not query_parts and fallback_query:
        query = fallback_query
    else:
        query = " ".join(query_parts) if query_parts else title[:80]

    return ParsedWatch(brand=brand, model=model, reference=reference, query=query)


def is_likely_watch(title: str) -> bool:
    lower = title.lower()
    if any(bad in lower for bad in (
        "book", "catalog", "poster", "magazine", "literature", "box only",
        "tool", "winder only", "display", "stand", "strap only", "link only",
        "bezel only", "comic", "camera", "scope", "fishing", "reel",
    )):
        # Still allow if brand+model strongly present
        parsed = parse_watch_title(title)
        return bool(parsed.brand and parsed.model)
    if "watch" in lower or "oyster" in lower or "chronograph" in lower:
        return True
    parsed = parse_watch_title(title)
    return bool(parsed.brand and (parsed.model or parsed.reference))