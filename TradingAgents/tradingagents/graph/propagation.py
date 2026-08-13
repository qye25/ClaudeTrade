# TradingAgents/graph/propagation.py

from typing import Any

from tradingagents.agents.utils.agent_states import (
    InvestDebateState,
    RiskDebateState,
)


class Propagator:
    """Handles state initialization and propagation through the graph."""

    def __init__(self, max_recur_limit=100):
        """Initialize with configuration parameters."""
        self.max_recur_limit = max_recur_limit
        self.portfolio_context = ""
        self.research_symbols: tuple[str, ...] = ()

    def set_portfolio_context(self, portfolio_context: str) -> None:
        """Set the current account context for the next graph run."""
        self.portfolio_context = portfolio_context or ""

    def set_research_symbols(self, research_symbols: list[str] | tuple[str, ...]) -> None:
        """Set the portfolio holdings that analysts should research deeply."""
        cleaned = []
        for symbol in research_symbols:
            value = str(symbol).upper().strip()
            if value and value not in cleaned:
                cleaned.append(value)
        self.research_symbols = tuple(cleaned)

    def create_initial_state(
        self,
        company_name: str,
        trade_date: str,
        asset_type: str = "stock",
        past_context: str = "",
        instrument_context: str = "",
        portfolio_context: str = "",
        research_symbols: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        """Create the initial state for the agent graph."""
        selected_research = tuple(research_symbols or self.research_symbols)
        return {
            "messages": [("human", company_name)],
            "company_of_interest": company_name,
            "asset_type": asset_type,
            "instrument_context": instrument_context,
            "trade_date": str(trade_date),
            "past_context": past_context,
            "portfolio_context": portfolio_context or self.portfolio_context,
            "research_symbols": selected_research,
            "investment_debate_state": InvestDebateState(
                {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "current_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "risk_debate_state": RiskDebateState(
                {
                    "aggressive_history": "",
                    "conservative_history": "",
                    "neutral_history": "",
                    "history": "",
                    "latest_speaker": "",
                    "current_aggressive_response": "",
                    "current_conservative_response": "",
                    "current_neutral_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "market_report": "",
            "fundamentals_report": "",
            "sentiment_report": "",
            "news_report": "",
        }

    def get_graph_args(self, callbacks: list | None = None) -> dict[str, Any]:
        """Get arguments for the graph invocation."""
        config = {"recursion_limit": self.max_recur_limit}
        if callbacks:
            config["callbacks"] = callbacks
        return {
            "stream_mode": "values",
            "config": config,
        }
