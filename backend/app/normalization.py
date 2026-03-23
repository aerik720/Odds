from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedMarket:
    market_type: str
    spec: str
    outcome: str


_OUTCOME_MAP = {
    "1x2": {"1": "home", "x": "draw", "2": "away"},
    "ou": {"over": "over", "under": "under"},
}


def normalize_outcome(market_type: str, raw_outcome: str) -> str:
    key = market_type.lower().strip()
    raw = raw_outcome.lower().strip()
    if key in _OUTCOME_MAP and raw in _OUTCOME_MAP[key]:
        return _OUTCOME_MAP[key][raw]
    return raw


def normalize_market(
    market_type: str, spec: str, raw_outcome: str
) -> NormalizedMarket:
    return NormalizedMarket(
        market_type=market_type.lower().strip(),
        spec=spec.strip(),
        outcome=normalize_outcome(market_type, raw_outcome),
    )
