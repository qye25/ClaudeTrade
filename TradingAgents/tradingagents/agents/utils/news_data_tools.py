from datetime import date, timedelta
import os
from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_news(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve news data for a given ticker symbol.

    The requested window is capped by TRADINGAGENTS_NEWS_MAX_LOOKBACK_DAYS
    (default 14 days) to keep news context bounded. Set the environment
    variable to override the cap for deeper research runs.
    """
    try:
        max_days = max(3, int(os.getenv("TRADINGAGENTS_NEWS_MAX_LOOKBACK_DAYS", "14")))
    except ValueError:
        max_days = 14

    try:
        end = date.fromisoformat(end_date)
        start = date.fromisoformat(start_date)
        capped_start = max(start, end - timedelta(days=max_days))
        start_date = capped_start.isoformat()
    except ValueError:
        pass

    return route_to_vendor("get_news", ticker, start_date, end_date)


@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int | None, "Days to look back; omit to use the configured default"] = None,
    limit: Annotated[int | None, "Max articles to return; omit to use the configured default"] = None,
) -> str:
    """
    Retrieve global news data.
    Uses the configured news_data vendor. Defaults for look_back_days and
    limit come from DEFAULT_CONFIG (global_news_lookback_days,
    global_news_article_limit); pass explicit values to override.
    """
    return route_to_vendor("get_global_news", curr_date, look_back_days, limit)


@tool
def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """
    Retrieve insider transaction information about a company.
    Uses the configured news_data vendor.
    """
    return route_to_vendor("get_insider_transactions", ticker)
