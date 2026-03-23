from decimal import Decimal

from .surebet import OddInput


def sample_odds() -> list[OddInput]:
    # Two markets: one surebet, one not
    return [
        # Market A (surebet): 1X2 with implied sum < 1
        OddInput("market-a", "home", Decimal("2.20"), "BookieA"),
        OddInput("market-a", "draw", Decimal("3.60"), "BookieB"),
        OddInput("market-a", "away", Decimal("3.60"), "BookieC"),
        # Market B (no surebet)
        OddInput("market-b", "over", Decimal("1.90"), "BookieA"),
        OddInput("market-b", "under", Decimal("1.90"), "BookieB"),
    ]
