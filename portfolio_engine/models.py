from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def q(value: Any, places: str = "0.0001") -> Decimal:
    return Decimal(str(value)).quantize(Decimal(places), rounding=ROUND_HALF_UP)


@dataclass
class TaxLot:
    symbol: str
    quantity: Decimal
    cost_basis: Decimal
    acquisition_date: str
    lot_id: str | None = None
    current_price: Decimal | None = None
    current_value: Decimal | None = None
    unrealized_gain_loss: Decimal | None = None
    realized_gain_loss: Decimal | None = None
    term: str = "unknown"
    wash_sale_status: str = "UNKNOWN"

    @property
    def is_long_term(self) -> bool:
        if not self.acquisition_date:
            return False
        try:
            acq = date.fromisoformat(self.acquisition_date)
            days = (date.today() - acq).days
            return days >= 365
        except ValueError:
            return False


@dataclass
class Position:
    symbol: str
    quantity: Decimal
    last_price: Decimal
    market_value: Decimal
    weight: Decimal
    effective_leverage_multiplier: Decimal = Decimal("1")
    effective_leverage_contribution: Decimal = Decimal("0")
    tax_lots: list[TaxLot] = field(default_factory=list)

    @classmethod
    def _parse_tax_lots(cls, symbol: str, lot_rows: Any) -> list[TaxLot]:
        if not isinstance(lot_rows, list):
            return []

        lots: list[TaxLot] = []
        for lot in lot_rows:
            if not isinstance(lot, dict):
                continue
            quantity = Decimal(str(lot.get("quantity", 0)))
            if quantity == 0:
                continue
            acquisition_date = str(
                lot.get("acquisition_date")
                or lot.get("acquired_at")
                or lot.get("date_acquired")
                or lot.get("date")
                or ""
            )
            current_value = lot.get("current_value")
            current_price = lot.get("current_price")
            lots.append(
                TaxLot(
                    symbol=(str(lot.get("symbol") or symbol)).upper(),
                    quantity=q(quantity),
                    cost_basis=q(lot.get("cost_basis", 0)),
                    acquisition_date=acquisition_date,
                    lot_id=str(lot.get("lot_id") or lot.get("id") or "") or None,
                    current_price=q(current_price) if current_price is not None else None,
                    current_value=q(current_value) if current_value is not None else None,
                    unrealized_gain_loss=q(lot.get("unrealized_gain_loss", 0)) if lot.get("unrealized_gain_loss") is not None else None,
                    realized_gain_loss=q(lot.get("realized_gain_loss", 0)) if lot.get("realized_gain_loss") is not None else None,
                    term=str(lot.get("term") or "unknown").lower(),
                    wash_sale_status=str(lot.get("wash_sale_status") or "UNKNOWN").upper(),
                )
            )
        return lots

    @classmethod
    def from_robinhood_position(cls, position: dict[str, Any], quote_map: dict[str, Decimal], portfolio_value: Decimal, lot_rows: Any = None):
        symbol = str(position.get("symbol") or "").upper()
        quantity = Decimal(str(position.get("quantity", 0)))
        last_price = quote_map.get(symbol, Decimal(str(position.get("last_price", 0))))
        market_value = Decimal(str(position.get("market_value", quantity * last_price)))
        weight = q(market_value / portfolio_value) if portfolio_value != 0 else Decimal("0")
        multiplier = {
            "UPRO": Decimal("3"),
            "DFEN": Decimal("3"),
            "NFLX": Decimal("1"),
            "RKLB": Decimal("1"),
            "TSLA": Decimal("1"),
        }.get(symbol, Decimal("1"))
        leverage_contribution = q(weight * multiplier)
        return cls(
            symbol=symbol,
            quantity=quantity,
            last_price=q(last_price),
            market_value=q(market_value),
            weight=weight,
            effective_leverage_multiplier=multiplier,
            effective_leverage_contribution=leverage_contribution,
            tax_lots=cls._parse_tax_lots(symbol, lot_rows),
        )


@dataclass
class Portfolio:
    portfolio_value: Decimal
    cash: Decimal
    buying_power: Decimal
    positions: list[Position]

    @classmethod
    def from_robinhood_payload(
        cls,
        payload: dict[str, Any],
    ) -> "Portfolio":
        """
        Build Portfolio from ClaudeTrade's normalized Robinhood payload.

        Expected normalized structure:

        {
            "portfolio_value": "1037.60",
            "buying_power": "0.00",
            "positions": {
                "NFLX": {
                    "quantity": "...",
                    "last_price": "...",
                    "market_value": "...",
                    "weight": "...",
                    "leverage_multiplier": "...",
                    "effective_leverage_contribution": "..."
                },
                ...
            }
        }
        """

        if not isinstance(payload, dict):
            raise TypeError(
                "Portfolio payload must be a dictionary."
            )

        # ---------------------------------------------------------
        # Portfolio-level values
        # ---------------------------------------------------------

        portfolio_value = Decimal(
            str(
                payload.get(
                    "portfolio_value",
                    "0",
                )
                or "0"
            )
        )

        buying_power = Decimal(
            str(
                payload.get(
                    "buying_power",
                    "0",
                )
                or "0"
            )
        )

        # Normalized payload does not currently expose cash
        # separately, so default it to zero.
        cash = Decimal(
            str(
                payload.get(
                    "cash",
                    "0",
                )
                or "0"
            )
        )

        # ---------------------------------------------------------
        # Positions
        # ---------------------------------------------------------

        positions_block = payload.get(
            "positions",
            {},
        )

        if not isinstance(positions_block, dict):
            positions_block = {}

        normalized_positions: list[Position] = []

        for symbol, row in positions_block.items():

            if not isinstance(row, dict):
                continue

            symbol = str(symbol).upper().strip()

            if not symbol:
                continue

            quantity = Decimal(
                str(
                    row.get(
                        "quantity",
                        "0",
                    )
                    or "0"
                )
            )

            last_price = Decimal(
                str(
                    row.get(
                        "last_price",
                        "0",
                    )
                    or "0"
                )
            )

            market_value = Decimal(
                str(
                    row.get(
                        "market_value",
                        "0",
                    )
                    or "0"
                )
            )

            weight = Decimal(
                str(
                    row.get(
                        "weight",
                        "0",
                    )
                    or "0"
                )
            )

            leverage_multiplier = Decimal(
                str(
                    row.get(
                        "leverage_multiplier",
                        "1",
                    )
                    or "1"
                )
            )

            effective_leverage_contribution = Decimal(
                str(
                    row.get(
                        "effective_leverage_contribution",
                        weight * leverage_multiplier,
                    )
                    or "0"
                )
            )

            normalized_positions.append(
                Position(
                    symbol=symbol,
                    quantity=quantity,
                    last_price=q(last_price),
                    market_value=q(market_value),
                    weight=weight,
                    effective_leverage_multiplier=leverage_multiplier,
                    effective_leverage_contribution=(
                        effective_leverage_contribution
                    ),
                    tax_lots=[],
                )
            )

        # ---------------------------------------------------------
        # Recalculate weights from actual position values
        # ---------------------------------------------------------
        #
        # This prevents stale/incorrect weights from propagating
        # into the risk engine.
        #
        # Use the normalized portfolio value when available.
        # ---------------------------------------------------------

        total_position_value = sum(
            (
                position.market_value
                for position in normalized_positions
            ),
            Decimal("0"),
        )

        denominator = (
            portfolio_value
            if portfolio_value > 0
            else total_position_value
        )

        if denominator > 0:
            for position in normalized_positions:

                position.weight = q(
                    position.market_value / denominator
                )

                position.effective_leverage_contribution = q(
                    position.weight
                    * position.effective_leverage_multiplier
                )

        return cls(
            portfolio_value=q(portfolio_value),
            cash=q(cash),
            buying_power=q(buying_power),
            positions=normalized_positions,
        )
    
    @property
    def total_effective_leverage(self) -> Decimal:
        return sum((p.effective_leverage_contribution for p in self.positions), Decimal("0"))
