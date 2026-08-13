from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "TradingAgents" / ".env")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark.strategies.mechanical import MechanicalStrategy
from benchmark.strategies.single_gemini import SingleGeminiStrategy
from benchmark.strategies.tradingagents import TradingAgentsStrategy


DEFAULT_UNIVERSE = ["UPRO", "TSLA", "RKLB", "NFLX", "DFEN"]


def run_single_symbol(symbol: str, timestamp: str) -> dict[str, Any]:
    market_data = {"close": 100.0}
    news = []
    sentiment = {"score": 0.2}
    fundamentals = {"pe_ratio": 18.0}

    strategies = {
        "tradingagents": TradingAgentsStrategy(),
        "single_gemini": SingleGeminiStrategy(),
        "mechanical": MechanicalStrategy(),
    }

    results = {}
    for name, strategy in strategies.items():
        decision = strategy.analyze(
            symbol=symbol,
            timestamp=timestamp,
            market_data=market_data,
            news=news,
            sentiment=sentiment,
            fundamentals=fundamentals,
        )
        results[name] = decision.as_dict()

    output = {
        "symbol": symbol,
        "timestamp": timestamp,
        "results": results,
    }
    output_dir = Path(__file__).resolve().parent / "results"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{symbol}_{timestamp[:10]}.json"
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return output


if __name__ == "__main__":
    sample = run_single_symbol("RKLB", "2026-08-11T10:00:00")
    print(json.dumps(sample, indent=2))
