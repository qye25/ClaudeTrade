from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
TRADINGAGENTS_ROOT = ROOT / "TradingAgents"

# Always use the repository's TradingAgents source instead of a stale package
# installed in the virtual environment.
if str(TRADINGAGENTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TRADINGAGENTS_ROOT))

load_dotenv(TRADINGAGENTS_ROOT / ".env")

from portfolio_engine.models import Portfolio
from robinhood_agent.client import (
    LIVE_ORDER_EXECUTION,
    ROBINHOOD_MCP_URL,
    READ_ONLY_TOOLS,
    TOKEN_FILE,
    FileTokenStorage,
    callback_handler,
    redirect_handler,
    read_live_portfolio,
    select_agentic_account,
)

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


def build_portfolio_context(portfolio: Portfolio) -> str:
    """Create concise account context for TradingAgents prompts."""
    lines = [
        f"Portfolio value: ${portfolio.portfolio_value}",
        f"Cash: ${portfolio.cash}",
        f"Buying power: ${portfolio.buying_power}",
        f"Effective leverage: {portfolio.total_effective_leverage}x",
        "",
        "Positions:",
    ]

    for position in sorted(
        portfolio.positions,
        key=lambda p: p.market_value,
        reverse=True,
    ):
        lines.append(
            "- "
            f"{position.symbol}: "
            f"weight={position.weight}, "
            f"quantity={position.quantity}, "
            f"market_value=${position.market_value}, "
            f"leverage={position.effective_leverage_multiplier}x"
        )

        if position.tax_lots:
            for lot in position.tax_lots:
                lines.append(
                    "  lot: "
                    f"qty={lot.quantity}, "
                    f"cost_basis=${lot.cost_basis}, "
                    f"acquired={lot.acquisition_date}, "
                    f"term={lot.term}, "
                    f"wash_sale={lot.wash_sale_status}"
                )

    return "\n".join(lines)


async def read_portfolio_and_run(symbol: str | None = None) -> None:
    if LIVE_ORDER_EXECUTION:
        raise RuntimeError(
            "Refusing to start: LIVE_ORDER_EXECUTION must be False."
        )

    storage = FileTokenStorage(TOKEN_FILE)

    from httpx2 import AsyncClient
    from pydantic import AnyUrl
    from mcp import ClientSession
    from mcp.client.auth import OAuthClientProvider
    from mcp.client.streamable_http import streamable_http_client
    from mcp.shared.auth import OAuthClientMetadata

    oauth_provider = OAuthClientProvider(
        server_url=ROBINHOOD_MCP_URL,
        client_metadata=OAuthClientMetadata(
            client_name="ClaudeTrade TradingAgents Live Reader",
            redirect_uris=[AnyUrl("http://localhost:8765/callback")],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
        ),
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )

    async with AsyncClient(
        auth=oauth_provider,
        follow_redirects=True,
    ) as http_client:
        async with streamable_http_client(
            ROBINHOOD_MCP_URL,
            http_client=http_client,
            terminate_on_close=False,
        ) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                tools = await session.list_tools()
                tool_names = {tool.name for tool in tools.tools}
                missing = READ_ONLY_TOOLS - tool_names
                if missing:
                    raise RuntimeError(
                        "Robinhood MCP is missing required read-only tools: "
                        f"{sorted(missing)}"
                    )

                account_number = await select_agentic_account(session)
                payload = await read_live_portfolio(
                    session,
                    account_number,
                )
                portfolio = Portfolio.from_robinhood_payload(payload)

                if not portfolio.positions:
                    raise RuntimeError(
                        "No equity positions were found in the live portfolio."
                    )

                anchor = symbol.upper() if symbol else max(
                    portfolio.positions,
                    key=lambda p: p.market_value,
                ).symbol

                known_symbols = {p.symbol for p in portfolio.positions}
                if anchor not in known_symbols:
                    raise ValueError(
                        f"Anchor symbol {anchor} is not in the live portfolio. "
                        f"Available: {sorted(known_symbols)}"
                    )

                context = build_portfolio_context(portfolio)

                config = DEFAULT_CONFIG.copy()
                config["llm_provider"] = "google"
                config["deep_think_llm"] = os.getenv(
                    "TRADINGAGENTS_DEEP_THINK_LLM",
                    config.get("deep_think_llm", "gemini-3.1-flash-lite"),
                )
                config["quick_think_llm"] = os.getenv(
                    "TRADINGAGENTS_QUICK_THINK_LLM",
                    config.get("quick_think_llm", "gemini-3.1-flash-lite"),
                )
                config["backend_url"] = None

                graph = TradingAgentsGraph(
                    selected_analysts=(
                        "market",
                        "social",
                        "news",
                        "fundamentals",
                    ),
                    debug=False,
                    config=config,
                )

                graph.propagator.set_portfolio_context(context)

                print("=" * 72)
                print("TRADINGAGENTS — LIVE ROBINHOOD PORTFOLIO / READ ONLY")
                print("=" * 72)
                print(f"TradingAgents source: {TRADINGAGENTS_ROOT}")
                print(f"Portfolio value: ${portfolio.portfolio_value}")
                print(f"Buying power:    ${portfolio.buying_power}")
                print(f"Research anchor: {anchor}")
                print()
                print(context)
                print()
                print("Running TradingAgents...")

                _, decision = graph.propagate(
                    anchor,
                    date.today().isoformat(),
                    asset_type="stock",
                )

                print()
                print("=" * 72)
                print("TRADINGAGENTS FINAL PORTFOLIO DECISION")
                print("=" * 72)
                print(decision)
                print()
                print("LIVE ORDER EXECUTION: DISABLED")
                print("=" * 72)


if __name__ == "__main__":
    selected_symbol = sys.argv[1].upper() if len(sys.argv) > 1 else None
    asyncio.run(read_portfolio_and_run(selected_symbol))
