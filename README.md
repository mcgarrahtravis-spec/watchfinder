# WatchFinder

Scan auction sites for watches and compare them against secondary-market comps to surface flip candidates.

## What it does

1. Pulls live auction lots from:
   - **HiBid** (GraphQL search — works well)
   - **Catawiki** (search page + bids API — works well)
   - **LiveAuctioneers** (best-effort; often blocked by bot protection)
   - Optional **CSV/JSON import** for lots you already collected
2. Builds a market value estimate from:
   - Built-in **reference price ranges** for popular models
   - Best-effort **eBay sold** scrape
   - Best-effort **Chrono24** asking-price scrape
3. Scores deals after estimated buyer premium + shipping
4. Shows results in a CLI table or a local web dashboard

> Respect each site’s terms of use. This tool is for personal research, uses polite rate limits, and is not a bypass for paid data access. eBay and Chrono24 frequently block datacenter IPs — reference comps keep the workflow useful when live comps fail.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Offline demo (no live auction calls)
python -m watchfinder -c config.yaml -q Rolex -q Seiko --json /tmp/deals.json
# Tip: set sources.hibid/catawiki false and sources.csv_path to
# watchfinder/data/demo_lots.json for a fully offline run.

# Live scan
cp config.example.yaml config.yaml   # edit queries / thresholds
python -m watchfinder

# Web UI
python -m watchfinder --serve --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000`.

## Config

See `config.example.yaml`:

- `queries` — brands/models to hunt
- `deal.min_margin_pct` — default 18% after fees
- `deal.buyer_premium_pct` — per-source fee assumptions
- `sources.csv_path` — import your own lot list

### CSV / JSON import columns

`title`, `url`, `current_bid`, `currency`, `source`, `source_id`, `bid_count`, `location`, `auction_house`, `image_url`

## Verdicts

| Verdict | Meaning |
|---|---|
| `worth_a_look` | Estimated margin clears your threshold after fees |
| `borderline` | Close — verify condition, box/papers, authenticity |
| `needs_review` | Missing comps |
| `skip` | Already at/above market after fees |

## Notes on comps

- Chrono24 prices are **asking** prices (usually high). The scorer applies a haircut when comps lean on asks.
- Reference ranges are approximate guides for popular references — always verify the exact reference, condition, and completeness before bidding.
- Buyer premiums vary by auction house; adjust `config.yaml` for houses you use often.

## Tests

```bash
PYTHONPATH=. pytest watchfinder/tests -q
```
