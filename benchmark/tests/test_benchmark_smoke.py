from benchmark.strategies.base import StrategyDecision
from benchmark.strategies.mechanical import MechanicalStrategy


def test_mechanical_strategy_returns_standardized_decision():
    strategy = MechanicalStrategy()
    decision = strategy.analyze(
        symbol="RKLB",
        timestamp="2026-08-11T10:00:00",
        market_data={"close": 101.0},
        news=[],
        sentiment={"score": 0.5},
        fundamentals={"pe_ratio": 15.0},
    )

    assert isinstance(decision, StrategyDecision)
    assert decision.symbol == "RKLB"
    assert decision.action in {"BUY", "SELL", "HOLD"}
    assert 0.0 <= decision.confidence <= 1.0
