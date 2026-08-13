from __future__ import annotations

from typing import Any

from .base import StrategyDecision


class MechanicalStrategy:
    """Simple deterministic baseline that never calls a model."""

    def analyze(
        self,
        symbol: str,
        timestamp: str,
        market_data: dict[str, Any] | None = None,
        news: list[Any] | None = None,
        sentiment: dict[str, Any] | None = None,
        fundamentals: dict[str, Any] | None = None,
    ) -> StrategyDecision:
        market_data = market_data or {}
        sentiment = sentiment or {}
        fundamentals = fundamentals or {}

        close = float(market_data.get("close", 0.0) or 0.0)
        sentiment_score = float(sentiment.get("score", 0.0) or 0.0)
        pe_ratio = fundamentals.get("pe_ratio")

        if close <= 0:
            action = "HOLD"
            confidence = 0.05
            reason = "No usable market price available."
        elif sentiment_score > 0.25 and (pe_ratio is None or float(pe_ratio) < 30):
            action = "BUY"
            confidence = 0.62
            reason = "Simple trend and sentiment heuristic favors long exposure."
        elif sentiment_score < -0.25 or (pe_ratio is not None and float(pe_ratio) > 40):
            action = "SELL"
            confidence = 0.61
            reason = "Weak sentiment or stretched valuation argues for reducing risk."
        else:
            action = "HOLD"
            confidence = 0.5
            reason = "The baseline sees no strong directional edge."

        return StrategyDecision(
            symbol=symbol.upper(),
            timestamp=timestamp,
            action=action,
            confidence=confidence,
            target_weight=0.15,
            holding_period_days=20,
            reason=reason,
        )
