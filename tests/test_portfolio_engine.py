import json
from decimal import Decimal
from pathlib import Path

import pytest

from portfolio_engine import LIVE_ORDER_EXECUTION
from portfolio_engine.models import Portfolio, Position, TaxLot
from portfolio_engine.policy import load_policy
from portfolio_engine.risk_engine import RiskEngine
from portfolio_engine.tax_engine import TaxEngine

def test_from_robinhood_payload_handles_nested_buying_power():
    payload = {
        "portfolio": {
            "total_value": "1036.23",
            "equity_value": "1036.23",
            "cash": "0",
            "buying_power": {
                "buying_power": "0.0000",
                "unleveraged_buying_power": "0.0000",
                "display_currency": "USD",
            },
        },
        "positions": {"positions": []},
        "quotes": {"quotes": []},
        "tax_lots": {"lots": []},
    }

    portfolio = Portfolio.from_robinhood_payload(payload)

    assert portfolio.buying_power == Decimal("0.0000")
    
def test_normalize_portfolio_from_live_payload():
    payload = {
        "portfolio": {
            "market_value": "1038.65",
            "equity": "1038.65",
            "buying_power": "0",
        },
        "positions": {
            "positions": [
                {"symbol": "NFLX", "quantity": "10", "market_value": "430.00"},
                {"symbol": "UPRO", "quantity": "4", "market_value": "420.00"},
                {"symbol": "DFEN", "quantity": "2", "market_value": "188.65"},
            ],
        },
        "quotes": {
            "quotes": [
                {"symbol": "NFLX", "last_trade_price": "43.00"},
                {"symbol": "UPRO", "last_trade_price": "105.00"},
                {"symbol": "DFEN", "last_trade_price": "94.325"},
            ],
        },
    }

    portfolio = Portfolio.from_robinhood_payload(payload)

    assert portfolio.portfolio_value == Decimal("1038.65")
    assert {p.symbol for p in portfolio.positions} == {"NFLX", "UPRO", "DFEN"}
    assert portfolio.positions[0].weight == Decimal("0.4140")
    assert portfolio.positions[1].weight == Decimal("0.4044")


def test_risk_engine_rejects_violation_before_tax_consideration():
    risk = RiskEngine(load_policy())
    portfolio = Portfolio(
        portfolio_value=Decimal("1000"),
        cash=Decimal("0"),
        buying_power=Decimal("0"),
        positions=[
            Position(symbol="UPRO", quantity=Decimal("4"), last_price=Decimal("100"), market_value=Decimal("400"), weight=Decimal("0.40"), effective_leverage_multiplier=Decimal("3"), effective_leverage_contribution=Decimal("1.20")),
            Position(symbol="NFLX", quantity=Decimal("10"), last_price=Decimal("30"), market_value=Decimal("300"), weight=Decimal("0.30"), effective_leverage_multiplier=Decimal("1"), effective_leverage_contribution=Decimal("0.30")),
            Position(symbol="TSLA", quantity=Decimal("10"), last_price=Decimal("30"), market_value=Decimal("300"), weight=Decimal("0.30"), effective_leverage_multiplier=Decimal("1"), effective_leverage_contribution=Decimal("0.30")),
        ],
    )

    result = risk.evaluate(portfolio)

    assert result["allowed"] is False
    assert any("hard risk" in reason.lower() or "leverage" in reason.lower() for reason in result["reasons"])


def test_tax_engine_uses_lot_level_data():
    tax = TaxEngine(tax_year=2026)
    lots = [
        TaxLot(
            symbol="UPRO",
            quantity=Decimal("2"),
            cost_basis=Decimal("180"),
            acquisition_date="2025-01-15",
            lot_id="lot-1",
            current_price=Decimal("120"),
            current_value=Decimal("240"),
            unrealized_gain_loss=Decimal("60"),
            wash_sale_status="UNKNOWN",
        ),
        TaxLot(
            symbol="UPRO",
            quantity=Decimal("1"),
            cost_basis=Decimal("90"),
            acquisition_date="2025-06-15",
            lot_id="lot-2",
            current_price=Decimal("120"),
            current_value=Decimal("120"),
            unrealized_gain_loss=Decimal("30"),
            wash_sale_status="UNKNOWN",
        ),
    ]

    outcome = tax.evaluate_lots("UPRO", lots, position_quantity=Decimal("3"))

    assert outcome["quantity"] == Decimal("3")
    assert outcome["cost_basis_total"] == Decimal("270")
    assert outcome["current_value_total"] == Decimal("360")
    assert outcome["unrealized_gain_loss"] == Decimal("90")
    assert outcome["lot_count"] == 2
    assert outcome["term_breakdown"]["long_term"] == Decimal("2")


def test_tax_lot_parser_accepts_real_robinhood_payload_shape():
    payload = {
        "portfolio": {"market_value": "1000", "buying_power": "0"},
        "positions": {"positions": [{"symbol": "UPRO", "quantity": "3", "market_value": "360"}]},
        "tax_lots": {
            "lots": [
                {
                    "symbol": "UPRO",
                    "quantity": "2",
                    "cost_basis": "180",
                    "acquired_at": "2025-01-15",
                    "lot_id": "UPRO-001",
                    "current_price": "120",
                    "current_value": "240",
                    "unrealized_gain_loss": "60",
                    "wash_sale_status": "UNKNOWN",
                },
                {
                    "symbol": "UPRO",
                    "quantity": "1",
                    "cost_basis": "90",
                    "date_acquired": "2025-06-15",
                    "lot_id": "UPRO-002",
                    "current_price": "120",
                    "current_value": "120",
                    "unrealized_gain_loss": "30",
                    "wash_sale_status": "UNKNOWN",
                },
            ]
        },
    }

    portfolio = Portfolio.from_robinhood_payload(payload)

    assert len(portfolio.positions) == 1
    assert len(portfolio.positions[0].tax_lots) == 2
    assert portfolio.positions[0].tax_lots[0].symbol == "UPRO"
    assert portfolio.positions[0].tax_lots[0].cost_basis == Decimal("180")
    assert portfolio.positions[0].tax_lots[1].acquisition_date == "2025-06-15"


def test_policy_loader_includes_monitoring_and_execution_policy():
    policy = load_policy("portfolio_policy")

    assert policy["monitoring"]["frequency"] == "hourly"
    assert policy["rebalance"]["frequency"] == "daily"
    assert policy["risk"]["hard_breach_review"] == "immediate"
    assert policy["execution"]["regular_market_hours_only"] is True
    assert policy["order_type"]["default"] == "limit"
    assert policy["order_type"]["market_orders"] == "disabled"


def test_execution_guard_is_hard_closed():
    assert LIVE_ORDER_EXECUTION is False


def test_tax_engine_rejects_quantity_mismatch():
    tax = TaxEngine(tax_year=2026)
    lots = [
        TaxLot(
            symbol="UPRO",
            quantity=Decimal("1"),
            cost_basis=Decimal("90"),
            acquisition_date="2025-01-15",
            lot_id="lot-1",
            current_price=Decimal("120"),
            current_value=Decimal("120"),
            unrealized_gain_loss=Decimal("30"),
            wash_sale_status="UNKNOWN",
        )
    ]

    with pytest.raises(ValueError, match="quantity.*mismatch"):
        tax.evaluate_lots("UPRO", lots, position_quantity=Decimal("3"))


def test_tax_fixture_reconciles_live_lot_payloads():
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "tax_lot_fixtures.json"
    fixtures = json.loads(fixture_path.read_text())
    tax = TaxEngine(tax_year=2026)

    for symbol, entry in fixtures.items():
        lots = [
            TaxLot(
                symbol=symbol,
                quantity=Decimal(str(item["quantity"])),
                cost_basis=Decimal(str(item["cost_basis"])),
                acquisition_date=item["acquisition_date"],
                lot_id=item["lot_id"],
                current_price=Decimal(str(item["current_price"])),
                current_value=Decimal(str(item["current_value"])),
                unrealized_gain_loss=Decimal(str(item["unrealized_gain_loss"])),
                term=item["term"],
                wash_sale_status=item.get("wash_sale_status", "UNKNOWN"),
            )
            for item in entry["lots"]
        ]

        outcome = tax.evaluate_lots(symbol, lots, position_quantity=Decimal(str(entry["position_quantity"])))

        assert outcome["quantity"] == Decimal(str(entry["position_quantity"]))
        assert outcome["lot_count"] == len(entry["lots"])
