from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


@dataclass(frozen=True)
class OddInput:
    market_id: str
    outcome: str
    price_decimal: Decimal
    bookmaker: str


@dataclass(frozen=True)
class SurebetResult:
    market_id: str
    total_implied_prob: Decimal
    edge_pct: Decimal
    best_odds: dict[str, OddInput]


def find_surebets(odds: Iterable[OddInput]) -> list[SurebetResult]:
    # Group best odds by market and outcome
    best_by_market: dict[str, dict[str, OddInput]] = {}
    for odd in odds:
        if odd.price_decimal <= 1:
            continue
        market = best_by_market.setdefault(odd.market_id, {})
        current = market.get(odd.outcome)
        if current is None or odd.price_decimal > current.price_decimal:
            market[odd.outcome] = odd

    results: list[SurebetResult] = []
    for market_id, outcomes in best_by_market.items():
        if not outcomes:
            continue
        implied_sum = sum(Decimal(1) / o.price_decimal for o in outcomes.values())
        if implied_sum < 1:
            edge_pct = (Decimal(1) - implied_sum) * 100
            results.append(
                SurebetResult(
                    market_id=market_id,
                    total_implied_prob=implied_sum,
                    edge_pct=edge_pct,
                    best_odds=outcomes,
                )
            )
    return results


def stake_split(
    total_stake: Decimal, odds_by_outcome: dict[str, OddInput]
) -> dict[str, Decimal]:
    # Distribute stake proportional to implied probability
    implied = {k: Decimal(1) / v.price_decimal for k, v in odds_by_outcome.items()}
    total_implied = sum(implied.values())
    if total_implied == 0:
        return {k: Decimal(0) for k in odds_by_outcome}
    return {
        k: (total_stake * (p / total_implied)).quantize(Decimal("0.01"))
        for k, p in implied.items()
    }
