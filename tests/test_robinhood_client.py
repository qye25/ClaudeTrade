import asyncio

import pytest

from robinhood_agent.client import (
    LIVE_ORDER_EXECUTION,
    READ_ONLY_TOOLS,
    call_read_only,
    extract_symbols,
    normalize_portfolio,
    read_live_portfolio,
)


class FakeResult:
    def __init__(self, data):
        self.structured_content = data


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return FakeResult(self.responses[name])


def test_live_order_execution_is_disabled():
    assert LIVE_ORDER_EXECUTION is False


def test_read_only_allowlist_contains_expected_tools():
    assert "get_accounts" in READ_ONLY_TOOLS
    assert "get_portfolio" in READ_ONLY_TOOLS
    assert "get_equity_positions" in READ_ONLY_TOOLS
    assert "get_equity_quotes" in READ_ONLY_TOOLS
    assert "get_equity_tax_lots" in READ_ONLY_TOOLS


def test_call_read_only_blocks_non_read_only_tool():
    async def run():
        session = FakeSession({})

        with pytest.raises(RuntimeError, match="BLOCKED"):
            await call_read_only(
                session,
                "place_order",
                {"symbol": "AAPL"},
            )

        assert session.calls == []

    asyncio.run(run())


def test_extract_symbols_from_positions():
    positions = {
        "positions": [
            {"symbol": "AAPL", "quantity": "10"},
            {"symbol": "TSLA", "quantity": "5"},
            {"symbol": "upro", "quantity": "2"},
            {"symbol": "AAPL", "quantity": "3"},
            {"symbol": "", "quantity": "1"},
        ]
    }

    assert extract_symbols(positions) == [
        "AAPL",
        "TSLA",
        "UPRO",
    ]


def test_extract_symbols_empty_positions():
    assert extract_symbols({"positions": []}) == []


def test_normalize_portfolio():
    portfolio = {
        "total_value": "10000",
        "equity_value": "10000",
        "cash": "0",
        "buying_power": {
            "buying_power": "2000",
            "unleveraged_buying_power": "2000",
            "display_currency": "USD",
        },
    }

    positions = {
        "positions": [
            {
                "symbol": "AAPL",
                "quantity": "10",
            },
            {
                "symbol": "UPRO",
                "quantity": "10",
            },
        ]
    }

    quotes = {
        "results": [
            {
                "quote": {
                    "symbol": "AAPL",
                    "last_trade_price": "500",
                },
                "close": {
                    "symbol": "AAPL",
                    "price": "500",
                },
            },
            {
                "quote": {
                    "symbol": "UPRO",
                    "last_trade_price": "300",
                },
                "close": {
                    "symbol": "UPRO",
                    "price": "300",
                },
            },
        ]
    }

    normalized = normalize_portfolio(
        portfolio,
        positions,
        quotes,
    )

    assert normalized["portfolio_value"] == "10000.00"
    assert normalized["buying_power"] == "2000.00"

    assert normalized["positions"]["AAPL"]["quantity"] == "10"
    assert normalized["positions"]["AAPL"]["last_price"] == "500"

    assert normalized["positions"]["UPRO"]["quantity"] == "10"
    assert normalized["positions"]["UPRO"]["last_price"] == "300"

    assert normalized["positions"]["UPRO"]["leverage_multiplier"] == "3"
    assert normalized["positions"]["UPRO"]["weight"] == "0.3000"

def test_read_live_portfolio_discovers_symbols_and_tax_lots():
    async def run():
        responses = {
            "get_portfolio": {
                "portfolio_value": "10000",
                "buying_power": "2000",
            },
            "get_equity_positions": {
                "positions": [
                    {
                        "symbol": "AAPL",
                        "quantity": "10",
                        "market_value": "5000",
                    },
                    {
                        "symbol": "UPRO",
                        "quantity": "10",
                        "market_value": "3000",
                    },
                ]
            },
            "get_equity_quotes": {
                "quotes": [
                    {"symbol": "AAPL", "price": "500"},
                    {"symbol": "UPRO", "price": "300"},
                ]
            },
        }

        class TaxLotSession(FakeSession):
            async def call_tool(self, name, arguments):
                self.calls.append((name, arguments))

                if name == "get_equity_tax_lots":
                    symbol = arguments["symbol"]

                    return FakeResult(
                        {
                            "taxLots": [
                                {
                                    "symbol": symbol,
                                    "quantity": "10",
                                    "cost_basis": "4000",
                                }
                            ]
                        }
                    )

                return FakeResult(self.responses[name])

        session = TaxLotSession(responses)

        result = await read_live_portfolio(
            session,
            "TEST-ACCOUNT",
        )

        assert result["symbols"] == [
            "AAPL",
            "UPRO",
        ]

        assert "tax_lots" in result
        assert "lots" in result["tax_lots"]

        assert {
            lot["symbol"]
            for lot in result["tax_lots"]["lots"]
        } == {
            "AAPL",
            "UPRO",
        }

        quote_calls = [
            call
            for call in session.calls
            if call[0] == "get_equity_quotes"
        ]

        assert len(quote_calls) == 1

        assert quote_calls[0][1]["symbols"] == [
            "AAPL",
            "UPRO",
        ]

        tax_lot_calls = [
            call
            for call in session.calls
            if call[0] == "get_equity_tax_lots"
        ]

        assert len(tax_lot_calls) == 2

        assert {
            call[1]["symbol"]
            for call in tax_lot_calls
        } == {
            "AAPL",
            "UPRO",
        }

    asyncio.run(run())


def test_read_live_portfolio_does_not_use_hard_coded_symbols():
    async def run():
        responses = {
            "get_portfolio": {
                "portfolio_value": "5000",
                "buying_power": "1000",
            },
            "get_equity_positions": {
                "positions": [
                    {
                        "symbol": "MSFT",
                        "quantity": "5",
                        "market_value": "2500",
                    },
                    {
                        "symbol": "NVDA",
                        "quantity": "2",
                        "market_value": "1500",
                    },
                ]
            },
            "get_equity_quotes": {
                "quotes": [
                    {"symbol": "MSFT", "price": "500"},
                    {"symbol": "NVDA", "price": "750"},
                ]
            },
        }

        class DynamicSession(FakeSession):
            async def call_tool(self, name, arguments):
                self.calls.append((name, arguments))

                if name == "get_equity_tax_lots":
                    return FakeResult(
                        {
                            "taxLots": [
                                {
                                    "symbol": arguments["symbol"],
                                    "quantity": "1",
                                }
                            ]
                        }
                    )

                return FakeResult(self.responses[name])

        session = DynamicSession(responses)

        result = await read_live_portfolio(
            session,
            "TEST-ACCOUNT",
        )

        assert result["symbols"] == [
            "MSFT",
            "NVDA",
        ]

        quote_call = next(
            call
            for call in session.calls
            if call[0] == "get_equity_quotes"
        )

        assert quote_call[1]["symbols"] == [
            "MSFT",
            "NVDA",
        ]

        assert "UPRO" not in result["symbols"]
        assert "TSLA" not in result["symbols"]
        assert "RKLB" not in result["symbols"]
        assert "NFLX" not in result["symbols"]
        assert "DFEN" not in result["symbols"]

    asyncio.run(run())


def test_empty_portfolio_does_not_request_quotes_or_tax_lots():
    async def run():
        responses = {
            "get_portfolio": {
                "portfolio_value": "0",
                "buying_power": "1000",
            },
            "get_equity_positions": {
                "positions": []
            },
        }

        session = FakeSession(responses)

        result = await read_live_portfolio(
            session,
            "TEST-ACCOUNT",
        )

        assert result["symbols"] == []
        assert result["tax_lots"] == {"lots": []}

        called_tools = [
            call[0]
            for call in session.calls
        ]

        assert "get_portfolio" in called_tools
        assert "get_equity_positions" in called_tools
        assert "get_equity_quotes" not in called_tools
        assert "get_equity_tax_lots" not in called_tools

    asyncio.run(run())

def test_robinhood_payload_converts_to_portfolio():
    from decimal import Decimal

    from portfolio_engine.models import Portfolio

    payload = {
        "portfolio": {
            "market_value": "10000",
            "equity": "10000",
            "cash": "1000",
            "buying_power": "1000",
        },
        "positions": {
            "positions": [
                {
                    "symbol": "AAPL",
                    "quantity": "10",
                    "market_value": "5000",
                },
                {
                    "symbol": "UPRO",
                    "quantity": "10",
                    "market_value": "3000",
                },
            ]
        },
        "quotes": {
            "quotes": [
                {
                    "symbol": "AAPL",
                    "last_trade_price": "500",
                },
                {
                    "symbol": "UPRO",
                    "last_trade_price": "300",
                },
            ]
        },
        "tax_lots": {
            "lots": [
                {
                    "symbol": "AAPL",
                    "quantity": "10",
                    "cost_basis": "4000",
                    "acquired_at": "2025-01-15",
                    "lot_id": "AAPL-1",
                },
                {
                    "symbol": "UPRO",
                    "quantity": "10",
                    "cost_basis": "2500",
                    "acquired_at": "2025-06-15",
                    "lot_id": "UPRO-1",
                },
            ]
        },
    }

    portfolio = Portfolio.from_robinhood_payload(payload)

    assert portfolio.portfolio_value == Decimal("10000")
    assert portfolio.cash == Decimal("1000")
    assert portfolio.buying_power == Decimal("1000")

    assert {p.symbol for p in portfolio.positions} == {
        "AAPL",
        "UPRO",
    }

    upro = next(
        p for p in portfolio.positions
        if p.symbol == "UPRO"
    )

    assert upro.quantity == Decimal("10")
    assert upro.market_value == Decimal("3000")
    assert upro.effective_leverage_multiplier == Decimal("3")
    assert len(upro.tax_lots) == 1