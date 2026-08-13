from __future__ import annotations

from decimal import Decimal
from typing import Any

from .models import TaxLot


class TaxEngine:
    def __init__(self, tax_year: int = 2026):
        self.tax_year = tax_year

    def evaluate_lots(
        self,
        symbol: str,
        lots: list[TaxLot],
        *,
        position_quantity: Decimal | None = None,
    ) -> dict[str, Any]:
        if not lots:
            raise ValueError(f"No tax lots provided for {symbol}.")

        total_quantity = sum((lot.quantity for lot in lots), Decimal("0"))
        if position_quantity is not None and total_quantity != position_quantity:
            raise ValueError(
                f"Tax lot quantity mismatch for {symbol}: lots sum to {total_quantity}, "
                f"position quantity is {position_quantity}."
            )

        total_cost = sum((lot.cost_basis for lot in lots), Decimal("0"))
        total_value = sum((lot.current_value or Decimal("0") for lot in lots), Decimal("0"))
        total_unrealized = total_value - total_cost
        long_term = sum((Decimal("1") for lot in lots if lot.is_long_term), Decimal("0"))
        short_term = sum((Decimal("1") for lot in lots if not lot.is_long_term), Decimal("0"))

        return {
            "symbol": symbol,
            "quantity": total_quantity,
            "cost_basis_total": total_cost,
            "current_value_total": total_value,
            "unrealized_gain_loss": total_unrealized,
            "lot_count": len(lots),
            "term_breakdown": {
                "long_term": long_term,
                "short_term": short_term,
            },
            "estimated_tax_impact": {
                "label": "Estimated tax impact — not tax advice.",
                "federal_estimate": Decimal("0"),
                "washington_estimate": Decimal("0"),
                "niit_estimate": Decimal("0"),
            },
        }
