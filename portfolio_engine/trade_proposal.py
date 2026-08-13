from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


VALID_SIDES = {"BUY", "SELL", "HOLD"}


@dataclass
class TradeProposal:
    symbol: str
    side: str
    quantity: Decimal
    reason: str = ""
    confidence: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        self.symbol = self.symbol.upper().strip()
        self.side = self.side.upper().strip()
        self.quantity = Decimal(str(self.quantity))
        self.confidence = Decimal(str(self.confidence))

        if self.side not in VALID_SIDES:
            raise ValueError(
                f"Invalid trade side: {self.side}. "
                f"Expected one of {sorted(VALID_SIDES)}."
            )

        if self.quantity < 0:
            raise ValueError("Trade quantity cannot be negative.")

        if not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError(
                "Confidence must be between 0 and 1."
            )

        if self.side == "HOLD":
            self.quantity = Decimal("0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "quantity": str(self.quantity),
            "reason": self.reason,
            "confidence": str(self.confidence),
        }