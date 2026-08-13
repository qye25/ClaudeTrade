from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "TradingAgents" / ".env")

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

from .base import StrategyDecision


class TradingAgentsStrategy:
    """Wrap the local TradingAgents graph into the benchmark interface."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = (config or DEFAULT_CONFIG.copy())
        self.config["llm_provider"] = "google"
        self.config["deep_think_llm"] = os.getenv(
            "TRADINGAGENTS_DEEP_THINK_LLM",
            self.config.get("deep_think_llm", "gemini-3.1-flash-lite"),
        )
        self.config["quick_think_llm"] = os.getenv(
            "TRADINGAGENTS_QUICK_THINK_LLM",
            self.config.get("quick_think_llm", "gemini-3.1-flash-lite"),
        )
        self.config["backend_url"] = None

    def analyze(
        self,
        symbol: str,
        timestamp: str,
        market_data: dict[str, Any] | None = None,
        news: list[Any] | None = None,
        sentiment: dict[str, Any] | None = None,
        fundamentals: dict[str, Any] | None = None,
    ) -> StrategyDecision:
        graph = TradingAgentsGraph(
            selected_analysts=("market", "social", "news", "fundamentals"),
            debug=False,
            config=self.config,
        )
        _, decision = graph.propagate(symbol, timestamp[:10], asset_type="stock")

        decision_dict = getattr(decision, "dict", lambda: {})()
        if not decision_dict:
            decision_dict = getattr(decision, "model_dump", lambda: {})()
        if not decision_dict:
            decision_dict = {
                "action": "HOLD",
                "confidence": 0.5,
                "target_weight": 0.15,
                "holding_period_days": 20,
                "reason": str(decision),
            }

        action = str(decision_dict.get("action", "HOLD")).upper()
        if action not in {"BUY", "SELL", "HOLD"}:
            action = "HOLD"

        confidence = float(decision_dict.get("confidence", 0.5) or 0.5)
        target_weight = float(decision_dict.get("target_weight", 0.15) or 0.15)
        holding_period_days = int(decision_dict.get("holding_period_days", 20) or 20)
        reason = str(decision_dict.get("reason", str(decision)))

        return StrategyDecision(
            symbol=symbol.upper(),
            timestamp=timestamp,
            action=action,
            confidence=max(0.0, min(1.0, confidence)),
            target_weight=max(0.0, target_weight),
            holding_period_days=holding_period_days,
            reason=reason,
        )
