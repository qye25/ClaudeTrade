from __future__ import annotations

import os
from typing import Any

from .base import StrategyDecision


class SingleGeminiStrategy:
    """Thin wrapper around the same Google/Gemini model configured for this project."""

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("TRADINGAGENTS_DEEP_THINK_LLM", "gemini-3.1-flash-lite")

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
        news = news or []
        sentiment = sentiment or {}
        fundamentals = fundamentals or {}

        try:
            from google import genai

            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise RuntimeError("GOOGLE_API_KEY is not set")

            client = genai.Client(api_key=api_key)
            prompt = self._build_prompt(symbol, market_data, news, sentiment, fundamentals)
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            text = getattr(response, "text", None) or str(response)
            action = self._parse_action(text)
            confidence = self._parse_confidence(text)
            reason = text.strip()[:400]
        except Exception:
            action = "HOLD"
            confidence = 0.35
            reason = "Gemini call unavailable; strategy failed open to a neutral HOLD."

        return StrategyDecision(
            symbol=symbol.upper(),
            timestamp=timestamp,
            action=action,
            confidence=confidence,
            target_weight=0.15,
            holding_period_days=20,
            reason=reason,
        )

    @staticmethod
    def _build_prompt(symbol: str, market_data: dict[str, Any], news: list[Any], sentiment: dict[str, Any], fundamentals: dict[str, Any]) -> str:
        close = market_data.get("close")
        sentiment_score = sentiment.get("score", 0)
        pe_ratio = fundamentals.get("pe_ratio")
        news_count = len(news)
        return (
            f"You are a trading analyst. Return only a JSON object with fields: "
            f"action (BUY/SELL/HOLD), confidence (0 to 1), reason. "
            f"Analyze {symbol}. Price={close}. News_count={news_count}. "
            f"Sentiment_score={sentiment_score}. PE_ratio={pe_ratio}. "
            f"Keep the answer concise and trading-focused."
        )

    @staticmethod
    def _parse_action(text: str) -> str:
        t = (text or "").upper()
        if "SELL" in t:
            return "SELL"
        if "BUY" in t:
            return "BUY"
        return "HOLD"

    @staticmethod
    def _parse_confidence(text: str) -> float:
        try:
            import re
            match = re.search(r"confidence\s*[:=]\s*([0-9]*\.?[0-9]+)", text, flags=re.I)
            if match:
                value = float(match.group(1))
                return max(0.0, min(1.0, value))
        except Exception:
            pass
        return 0.5
