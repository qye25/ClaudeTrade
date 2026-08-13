import os
from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"] = 30,
) -> str:
    """
    Retrieve a single technical indicator for a given ticker symbol.

    The requested lookback is capped by TRADINGAGENTS_INDICATOR_MAX_LOOKBACK_DAYS
    (default 60 days) to prevent large indicator tables from consuming the LLM
    context window. Set the environment variable to override the cap.
    """
    try:
        max_days = max(20, int(os.getenv("TRADINGAGENTS_INDICATOR_MAX_LOOKBACK_DAYS", "60")))
    except ValueError:
        max_days = 60
    try:
        look_back_days = min(max(1, int(look_back_days)), max_days)
    except (TypeError, ValueError):
        look_back_days = min(30, max_days)

    indicators = [i.strip().lower() for i in indicator.split(",") if i.strip()]
    results = []
    for ind in indicators:
        try:
            results.append(
                route_to_vendor(
                    "get_indicators",
                    symbol,
                    ind,
                    curr_date,
                    look_back_days,
                )
            )
        except ValueError as e:
            results.append(str(e))
    return "\n\n".join(results)
