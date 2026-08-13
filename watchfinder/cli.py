from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from watchfinder.config import load_config
from watchfinder.pipeline import run_scan


console = Console()


def _print_deals(result, min_verdict: str = "borderline") -> None:
    order = {"worth_a_look": 0, "borderline": 1, "needs_review": 2, "incomplete": 3, "skip": 4}
    min_rank = order.get(min_verdict, 1)
    deals = [d for d in result.deals if order.get(d.verdict, 9) <= min_rank]

    table = Table(title=f"Watch deals ({len(deals)} shown / {len(result.deals)} total)")
    table.add_column("Verdict")
    table.add_column("Source")
    table.add_column("Title", overflow="fold", max_width=44)
    table.add_column("Bid", justify="right")
    table.add_column("All-in", justify="right")
    table.add_column("Market", justify="right")
    table.add_column("Margin", justify="right")
    table.add_column("URL", overflow="fold", max_width=36)

    for deal in deals:
        lot = deal.lot
        table.add_row(
            deal.verdict,
            lot.source.value,
            lot.title[:80],
            f"${lot.current_bid:,.0f}" if lot.current_bid is not None else "—",
            f"${deal.all_in_cost:,.0f}" if deal.all_in_cost is not None else "—",
            f"${deal.market_value:,.0f}" if deal.market_value is not None else "—",
            f"{deal.margin_pct:.0%}" if deal.margin_pct is not None else "—",
            lot.url,
        )
    console.print(table)

    if result.errors:
        console.print("\n[yellow]Source warnings:[/yellow]")
        for err in result.errors:
            console.print(f"  • {err}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan auction sites for watch deals vs recent market comps."
    )
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help="Path to config.yaml (defaults to config.yaml / config.example.yaml)",
    )
    parser.add_argument(
        "-q",
        "--query",
        action="append",
        dest="queries",
        help="Search query (repeatable). Overrides config queries.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Write full ScanResult JSON to this path",
    )
    parser.add_argument(
        "--min-verdict",
        default="borderline",
        choices=["worth_a_look", "borderline", "needs_review", "incomplete", "skip"],
        help="Minimum verdict to print in the table",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Launch the web dashboard instead of a one-shot scan",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    if args.serve:
        import uvicorn
        from watchfinder.web.app import app

        uvicorn.run(app, host=args.host, port=args.port)
        return 0

    cfg = load_config(args.config)
    console.print(f"[bold]Scanning[/bold] queries={args.queries or cfg.queries}")
    result = run_scan(cfg, queries=args.queries)
    _print_deals(result, min_verdict=args.min_verdict)

    if args.json:
        args.json.write_text(result.model_dump_json(indent=2))
        console.print(f"Wrote {args.json}")

    worth = sum(1 for d in result.deals if d.verdict == "worth_a_look")
    console.print(
        f"\nLots: {len(result.lots)} | Worth a look: {worth} | Errors: {len(result.errors)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())