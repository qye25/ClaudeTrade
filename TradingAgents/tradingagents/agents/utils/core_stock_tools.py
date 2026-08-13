from datetime import date, timedelta
from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve stock price data (OHLCV) for a given ticker symbol.

    To prevent oversized LLM contexts, the requested history is capped by
    TRADINGAGENTS_MARKET_DATA_MAX_LOOKBACK_DAYS (default 180 days). Set the
    environment variable to override the cap for deeper research runs.
    Uses the configured core_stock_apis vendor.
    """
    try:
        max_days = max(30, int(__import__("os").getenv("TRADINGAGENTS_MARKET_DATA_MAX_LOOKBACK_DAYS", "180")))
    except ValueError:
        max_days = 180

    try:
        end = date.fromisoformat(end_date)
        start = date.fromisoformat(start_date)
        capped_start = max(start, end - timedelta(days=max_days))
        start_date = capped_start.isoformat()
    except ValueError:
        # Preserve the vendor's validation behavior for malformed dates.
        pass

    return route_to_vendor("get_stock_data", symbol, start_date, end_date)
