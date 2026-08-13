"""Deal scoring: auction ask vs recent market value."""

from __future__ import annotations

from watchfinder.config import DealConfig
from watchfinder.models import AuctionLot, DealOpportunity, MarketComps


def estimate_all_in_cost(lot: AuctionLot, cfg: DealConfig) -> float | None:
    if lot.current_bid is None:
        return None
    premium = cfg.buyer_premium_pct.get(lot.source.value, 0.15)
    return round(lot.current_bid * (1 + premium) + cfg.estimated_shipping_usd, 2)


def score_deal(
    lot: AuctionLot,
    comps: MarketComps | None,
    cfg: DealConfig,
) -> DealOpportunity:
    reasons: list[str] = []
    all_in = estimate_all_in_cost(lot, cfg)
    market = comps.median_price if comps else None

    if all_in is None:
        reasons.append("No current bid / price available")
        return DealOpportunity(
            lot=lot,
            comps=comps,
            verdict="incomplete",
            reasons=reasons,
        )

    if market is None or market <= 0:
        reasons.append("No usable comps — check manually")
        return DealOpportunity(
            lot=lot,
            comps=comps,
            all_in_cost=all_in,
            verdict="needs_review",
            score=0.1,
            reasons=reasons,
        )

    profit = round(market - all_in, 2)
    margin = profit / market
    premium = cfg.buyer_premium_pct.get(lot.source.value, 0.15)
    reasons.append(
        f"All-in ≈ ${all_in:,.0f} (bid ${lot.current_bid:,.0f} + {premium:.0%} premium + ${cfg.estimated_shipping_usd:.0f} ship)"
    )
    reasons.append(
        f"Market ≈ ${market:,.0f} from {comps.sample_size} comps"
        + (f" ({comps.notes})" if comps and comps.notes else "")
    )

    # Discount Chrono24-heavy comps slightly (asking prices skew high)
    chrono_heavy = False
    if comps and comps.comps:
        chrono_n = sum(1 for c in comps.comps if c.is_asking_price)
        chrono_heavy = chrono_n >= max(1, len(comps.comps) // 2)
    if chrono_heavy:
        market_adj = market * 0.92
        reasons.append("Comps lean on asking prices — applied 8% haircut")
        profit = round(market_adj - all_in, 2)
        margin = profit / market_adj
        market = market_adj

    if margin >= cfg.min_margin_pct and profit > 50:
        verdict = "worth_a_look"
        score = min(1.0, 0.5 + margin)
        reasons.append(f"Estimated margin {margin:.0%} (≥ {cfg.min_margin_pct:.0%} target)")
        if margin >= 0.5:
            reasons.append(
                "Very large spread — double-check authenticity, condition, and exact reference before bidding"
            )
    elif margin >= cfg.min_margin_pct * 0.6:
        verdict = "borderline"
        score = 0.35 + margin * 0.5
        reasons.append(f"Thin margin {margin:.0%} — verify condition & authenticity carefully")
    elif margin > 0:
        verdict = "skip"
        score = max(0.05, margin)
        reasons.append(f"Margin only {margin:.0%} after fees")
    else:
        verdict = "skip"
        score = 0.0
        reasons.append("Auction price already at/above market")

    # Soft boosts
    if lot.bid_count is not None and lot.bid_count <= 2 and margin > 0:
        score += 0.05
        reasons.append("Low competition so far")
    if lot.shipping_offered:
        score += 0.02

    return DealOpportunity(
        lot=lot,
        comps=comps,
        all_in_cost=all_in,
        market_value=round(market, 2) if market else None,
        estimated_profit=profit,
        margin_pct=round(margin, 4),
        score=round(min(score, 1.0), 3),
        verdict=verdict,
        reasons=reasons,
    )