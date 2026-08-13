from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Literal


Action = Literal["BUY", "SELL", "HOLD"]


@dataclass
class StrategyDecision:
    """Normalized decision payload used by every benchmark strategy."""

    symbol: str
    timestamp: str
    action: Action
    confidence: float
    target_weight: float
    holding_period_days: int
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:
        return self.as_dict().__str__()
