from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

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
                                min(Decimal("1"), cls._decimal(row.get("confidence", confidence))),
                            ),
                        )
                    )
                except (TypeError, ValueError):
                    continue

        # Ensure the AI cannot accidentally create a proposal for an empty
        # symbol. TradeProposal itself performs the remaining field validation.
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
