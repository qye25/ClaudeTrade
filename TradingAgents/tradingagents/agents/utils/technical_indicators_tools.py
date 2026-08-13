import os
from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "the current trading date in YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"] = 30,
) -> str:
    """Retrieve a single technical indicator with a bounded lookback window."""
    try:
        max_days = max(
            10,
            int(os.getenv("TRADINGAGENTS_INDICATOR_MAX_LOOKBACK_DAYS", "20")),
        )
    except ValueError:
        max_days = 20

    try:
        look_back_days = min(max(1, int(look_back_days)), max_days)
    except (TypeError, ValueError):
        look_back_days = max_days

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
