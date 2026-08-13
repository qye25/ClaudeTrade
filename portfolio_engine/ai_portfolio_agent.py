from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .models import Portfolio
from .trade_proposal import TradeProposal


@dataclass
class PortfolioDecision:
    """The investment decision produced by the AI portfolio agent.

    Investment choices are intentionally model-owned. This class normalizes the
    model output; it does not decide whether a trade is safe to execute.
    """

    thesis: str
    risk_assessment: str
    confidence: Decimal
    holding_period_days: int
    target_weights: dict[str, Decimal] = field(default_factory=dict)
    trades: list[TradeProposal] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "thesis": self.thesis,
            "risk_assessment": self.risk_assessment,
            "confidence": str(self.confidence),
            "holding_period_days": self.holding_period_days,
            "target_weights": {
                symbol: str(weight)
                for symbol, weight in self.target_weights.items()
            },
            "trades": [trade.to_dict() for trade in self.trades],
        }


class AIPortfolioAgent:
    """Use Gemini to make portfolio-level investment decisions.

    The agent receives the complete normalized portfolio and optional research
    context. It may choose targets and trades. Deterministic risk/execution
    code remains outside this class.
    """

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv(
            "TRADINGAGENTS_DEEP_THINK_LLM",
            "gemini-3.1-flash-lite",
        )
        self.api_key = os.getenv("GOOGLE_API_KEY")

    def decide(
        self,
        portfolio: Portfolio,
        *,
        market_data: dict[str, Any] | None = None,
        news: list[Any] | None = None,
        sentiment: dict[str, Any] | None = None,
        fundamentals: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> PortfolioDecision:
        if not self.api_key:
            raise RuntimeError("GOOGLE_API_KEY is not set")

        from google import genai

        client = genai.Client(api_key=self.api_key)
        prompt = self._build_prompt(
            portfolio,
            market_data or {},
            news or [],
            sentiment or {},
            fundamentals or {},
            timestamp or "",
        )

        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        text = getattr(response, "text", None) or str(response)
        payload = self._parse_json(text)
        return self._normalize_decision(payload, portfolio)

    @staticmethod
    def _build_prompt(
        portfolio: Portfolio,
        market_data: dict[str, Any],
        news: list[Any],
        sentiment: dict[str, Any],
        fundamentals: dict[str, Any],
        timestamp: str,
    ) -> str:
        positions = []
        for position in portfolio.positions:
            positions.append(
                {
                    "symbol": position.symbol,
                    "quantity": str(position.quantity),
                    "last_price": str(position.last_price),
                    "market_value": str(position.market_value),
                    "weight": str(position.weight),
                    "leverage_multiplier": str(position.effective_leverage_multiplier),
                    "tax_lots": [
                        {
                            "quantity": str(lot.quantity),
                            "cost_basis": str(lot.cost_basis),
                            "acquisition_date": lot.acquisition_date,
                            "term": lot.term,
                            "wash_sale_status": lot.wash_sale_status,
                        }
                        for lot in position.tax_lots
                    ],
                }
            )

        portfolio_state = {
            "portfolio_value": str(portfolio.portfolio_value),
            "cash": str(portfolio.cash),
            "buying_power": str(portfolio.buying_power),
            "effective_leverage": str(portfolio.total_effective_leverage),
            "positions": positions,
        }

        output_schema = {
            "thesis": "string",
            "risk_assessment": "string",
            "confidence": "number between 0 and 1",
            "holding_period_days": "integer",
            "target_weights": {"SYMBOL": "number between 0 and 1"},
            "trades": [
                {
                    "symbol": "string",
                    "side": "BUY|SELL|HOLD",
                    "quantity": "non-negative number",
                    "reason": "string",
                    "confidence": "number between 0 and 1",
                }
            ],
        }

        return f"""
You are the portfolio manager for an AI-native trading system.

Make the investment decision for the ENTIRE portfolio, not for one symbol.
You own the investment decision: portfolio thesis, target weights, trade
selection, quantities, confidence, and holding horizon.

Do not follow a pre-written allocation strategy. Do not assume that any
current position must be held. Consider concentration, leverage, liquidity,
tax lots, market conditions, news, sentiment, fundamentals, and the user's
existing exposure together.

IMPORTANT:
- Return ONLY valid JSON. No markdown and no commentary outside JSON.
- Use BUY, SELL, or HOLD for each proposed trade.
- HOLD trades must have quantity 0.
- target_weights are your desired portfolio weights after the proposed
  rebalance. You may include only symbols you want to explicitly target.
- Do not invent prices, positions, or cash that are absent from the input.
- A trade is a proposal, not an execution authorization.
- If the evidence is insufficient, prefer HOLD and explain why.
- Give a concise but complete sentence-level rationale for every trade.

Analysis timestamp: {timestamp}

CURRENT PORTFOLIO:
{json.dumps(portfolio_state, indent=2)}

MARKET DATA:
{json.dumps(market_data, default=str, indent=2)}

NEWS:
{json.dumps(news, default=str, indent=2)}

SENTIMENT:
{json.dumps(sentiment, default=str, indent=2)}

FUNDAMENTALS:
{json.dumps(fundamentals, default=str, indent=2)}

RETURN THIS JSON SHAPE:
{json.dumps(output_schema, indent=2)}
""".strip()

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        text = (text or "").strip()
        if not text:
            raise ValueError("AI portfolio agent returned an empty response")

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not match:
                raise ValueError("AI portfolio agent did not return valid JSON")
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise ValueError("AI portfolio agent returned malformed JSON") from exc

        if not isinstance(payload, dict):
            raise ValueError("AI portfolio agent response must be a JSON object")
        return payload

    @classmethod
    def _normalize_decision(
        cls,
        payload: dict[str, Any],
        portfolio: Portfolio,
    ) -> PortfolioDecision:
        confidence = cls._decimal(payload.get("confidence", 0))
        confidence = max(Decimal("0"), min(Decimal("1"), confidence))

        try:
            holding_period_days = int(payload.get("holding_period_days", 0) or 0)
        except (TypeError, ValueError):
            holding_period_days = 0
        holding_period_days = max(0, holding_period_days)

        target_weights: dict[str, Decimal] = {}
        raw_targets = payload.get("target_weights", {})
        if isinstance(raw_targets, dict):
            for symbol, weight in raw_targets.items():
                try:
                    parsed = cls._decimal(weight)
                except (TypeError, ValueError):
                    continue
                if parsed < 0:
                    continue
                target_weights[str(symbol).upper().strip()] = parsed

        trades: list[TradeProposal] = []
        raw_trades = payload.get("trades", [])
        if isinstance(raw_trades, list):
            for row in raw_trades:
                if not isinstance(row, dict):
                    continue
                try:
                    trades.append(
                        TradeProposal(
                            symbol=str(row.get("symbol", "")),
                            side=str(row.get("side", "HOLD")),
                            quantity=cls._decimal(row.get("quantity", 0)),
                            reason=str(row.get("reason", "")),
                            confidence=max(
                                Decimal("0"),
                                min("1", cls._decimal(row.get("confidence", confidence))),
                            ),
                        )
                    )
                except (TypeError, ValueError):
                    continue

        trades = [trade for trade in trades if trade.symbol]

        existing_symbols = {p.symbol for p in portfolio.positions}
        unknown_targets = [s for s in target_weights if not s]
        if unknown_targets:
            for symbol in unknown_targets:
                target_weights.pop(symbol, None)

        return PortfolioDecision(
            thesis=str(payload.get("thesis", "")),
            risk_assessment=str(payload.get("risk_assessment", "")),
            confidence=confidence,
            holding_period_days=holding_period_days,
            target_weights=target_weights,
            trades=trades,
        )

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        return Decimal(str(value))


async def _read_live_portfolio() -> Portfolio:
    """Read the real Robinhood portfolio through the existing read-only MCP path."""
    load_dotenv(Path(__file__).resolve().parents[1] / "TradingAgents" / ".env")

    from robinhood_agent.client import (
        LIVE_ORDER_EXECUTION,
        READ_ONLY_TOOLS,
        ROBINHOOD_MCP_URL,
        TOKEN_FILE,
        FileTokenStorage,
        OAuthClientMetadata,
        OAuthClientProvider,
        AnyUrl,
        ClientSession,
        AuthorizationCodeResult,
        httpx2,
        select_agentic_account,
        read_live_portfolio,
        redirect_handler,
        callback_handler,
        streamable_http_client,
    )

    if LIVE_ORDER_EXECUTION:
        raise RuntimeError("Refusing AI portfolio read: live execution must be disabled.")

    storage = FileTokenStorage(TOKEN_FILE)
    oauth_provider = OAuthClientProvider(
        server_url=ROBINHOOD_MCP_URL,
        client_metadata=OAuthClientMetadata(
            client_name="ClaudeTrade AI Portfolio Agent",
            redirect_uris=[AnyUrl("http://localhost:8765/callback")],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
        ),
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )

    async with httpx2.AsyncClient(
        auth=oauth_provider,
        follow_redirects=True,
    ) as http_client:
        async with streamable_http_client(
            ROBINHOOD_MCP_URL,
            http_client=http_client,
            terminate_on_close=False,
        ) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                tools = await session.list_tools()
                tool_names = {tool.name for tool in tools.tools}
                missing = READ_ONLY_TOOLS - tool_names
                if missing:
                    raise RuntimeError(
                        f"Robinhood MCP is missing required read-only tools: {sorted(missing)}"
                    )

                account_number = await select_agentic_account(session)
                payload = await read_live_portfolio(session, account_number)
                return Portfolio.from_robinhood_payload(payload)


async def _main() -> None:
    print("=" * 64)
    print("AI PORTFOLIO AGENT — READ ONLY")
    print("=" * 64)

    print("\n[1/2] Reading live Robinhood portfolio...")
    portfolio = await _read_live_portfolio()

    print(f"Portfolio value: ${portfolio.portfolio_value}")
    print(f"Buying power:    ${portfolio.buying_power}")
    print("\nPositions")
    print("-" * 64)
    for position in portfolio.positions:
        print(
            f"{position.symbol:<8} "
            f"weight={float(position.weight):>7.2%} "
            f"value=${position.market_value:>10} "
            f"leverage={position.effective_leverage_multiplier}x"
        )

    print("\n[2/2] Asking Gemini for the portfolio decision...")
    agent = AIPortfolioAgent()
    decision = agent.decide(portfolio)

    print("\n" + "=" * 64)
    print("AI THESIS")
    print("=" * 64)
    print(decision.thesis)

    print("\nRISK ASSESSMENT")
    print("-" * 64)
    print(decision.risk_assessment)

    print("\nTARGET WEIGHTS")
    print("-" * 64)
    for symbol, weight in decision.target_weights.items():
        print(f"{symbol:<8} {float(weight):>7.2%}")

    print("\nPROPOSED TRADES")
    print("-" * 64)
    if not decision.trades:
        print("No trades proposed.")
    else:
        for trade in decision.trades:
            print(
                f"{trade.side:<5} {trade.symbol:<8} "
                f"qty={trade.quantity} confidence={float(trade.confidence):.2%}"
            )
            print(f"  Reason: {trade.reason}")

    print("\n" + "=" * 64)
    print("AI SUMMARY")
    print("=" * 64)
    print(f"Confidence:     {float(decision.confidence):.2%}")
    print(f"Holding period: {decision.holding_period_days} days")
    print("\nLIVE ORDER EXECUTION: DISABLED")
    print("=" * 64)


if __name__ == "__main__":
    asyncio.run(_main())
