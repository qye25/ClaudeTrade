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
    def from_robinhood_payload(cls, payload: dict[str, Any]) -> "Portfolio":
        portfolio_data = payload.get("portfolio", {}) if isinstance(payload, dict) else {}
        if not isinstance(portfolio_data, dict):
            portfolio_data = {}

        portfolio_value = Decimal(str(portfolio_data.get("market_value", portfolio_data.get("equity", 0))))
        cash = Decimal(str(portfolio_data.get("cash", 0)))
        buying_power = Decimal(str(portfolio_data.get("buying_power", 0)))

        positions_block = payload.get("positions", {}) if isinstance(payload, dict) else {}
        if not isinstance(positions_block, dict):
            positions_block = {}
        position_rows = positions_block.get("positions", [])
        quote_rows = payload.get("quotes", {}).get("quotes", []) if isinstance(payload, dict) else []

        tax_lots_block = payload.get("tax_lots", {}) if isinstance(payload, dict) else {}
        if not isinstance(tax_lots_block, dict):
            tax_lots_block = {}
        tax_lots_rows = tax_lots_block.get("lots", [])
        tax_lot_index: dict[str, list[dict[str, Any]]] = {}
        for lot in tax_lots_rows:
            if not isinstance(lot, dict):
                continue
            symbol = str(lot.get("symbol") or "").upper()
            if symbol:
                tax_lot_index.setdefault(symbol, []).append(lot)

        quote_map = {}
        for item in quote_rows:
            symbol = str(item.get("symbol", "")).upper()
            if symbol:
                quote_map[symbol] = Decimal(str(item.get("last_trade_price", item.get("price", 0))))

        normalized_positions = []
        for pos in position_rows:
            symbol = str(pos.get("symbol", "")).upper()
            if not symbol:
                continue
            normalized_positions.append(
                Position.from_robinhood_position(pos, quote_map, portfolio_value, tax_lot_index.get(symbol, []))
            )

        if normalized_positions:
            total = sum((p.market_value for p in normalized_positions), Decimal("0"))
            if total > 0:
                for pos in normalized_positions:
                    pos.weight = q(pos.market_value / total)
                    pos.effective_leverage_contribution = q(pos.weight * pos.effective_leverage_multiplier)

        return cls(
            portfolio_value=q(portfolio_value),
            cash=q(cash),
            buying_power=q(buying_power),
            positions=normalized_positions,
        )

    @property
    def total_effective_leverage(self) -> Decimal:
        return sum((p.effective_leverage_contribution for p in self.positions), Decimal("0"))
