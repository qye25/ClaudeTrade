from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
TRADINGAGENTS_ROOT = ROOT / "TradingAgents"

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
    read_live_tax_lots,
    select_agentic_account,
)

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

VALID_ANALYSTS = {"market", "social", "news", "fundamentals"}
FAST_ANALYSTS = ("market", "news")
FULL_ANALYSTS = ("market", "social", "news", "fundamentals")
VALID_PROVIDERS = {
    "google",
    "openai",
    "anthropic",
    "groq",
    "cerebras",
    "openrouter",
    "mistral",
    "deepseek",
    "xai",
    "qwen",
    "qwen-cn",
    "glm",
    "glm-cn",
    "minimax",
    "minimax-cn",
    "kimi",
    "nvidia",
    "ollama",
    "openai_compatible",
}


def build_portfolio_context(portfolio: Portfolio) -> str:
    lines = [
        f"Portfolio value: ${portfolio.portfolio_value}",
        f"Cash: ${portfolio.cash}",
        f"Buying power: ${portfolio.buying_power}",
        f"Effective leverage: {portfolio.total_effective_leverage}x",
        "",
        "Positions:",
    ]
    for position in sorted(portfolio.positions, key=lambda p: p.market_value, reverse=True):
        lines.append(
            "- "
            f"{position.symbol}: weight={position.weight}, quantity={position.quantity}, "
            f"market_value=${position.market_value}, leverage={position.effective_leverage_multiplier}x"
        )
        if position.tax_lots:
            for lot in position.tax_lots:
                lines.append(
                    "  lot: "
                    f"qty={lot.quantity}, cost_basis=${lot.cost_basis}, acquired={lot.acquisition_date}, "
                    f"term={lot.term}, wash_sale={lot.wash_sale_status}"
                )
    return "\n".join(lines)


def resolve_run_config(mode: str) -> tuple[tuple[str, ...], dict]:
    requested_mode = mode.lower()
    if requested_mode not in {"fast", "full"}:
        raise ValueError("mode must be 'fast' or 'full'")

    config = DEFAULT_CONFIG.copy()
    env_analysts = os.getenv("TRADINGAGENTS_ANALYSTS", "").strip()
    env_provider = os.getenv("TRADINGAGENTS_LLM_PROVIDER", "google").strip().lower()
    env_thinking = os.getenv("TRADINGAGENTS_GOOGLE_THINKING_LEVEL", "").strip()

    if env_provider not in VALID_PROVIDERS:
        raise ValueError(
            f"Invalid provider '{env_provider}'. Valid choices: {sorted(VALID_PROVIDERS)}"
        )

    if requested_mode == "fast":
        analysts = FAST_ANALYSTS
        thinking = "minimal"
        config["max_debate_rounds"] = 1
        config["max_risk_discuss_rounds"] = 1
    else:
        raw = env_analysts or ",".join(FULL_ANALYSTS)
        analysts = tuple(item.strip() for item in raw.split(",") if item.strip())
        invalid = sorted(set(analysts) - VALID_ANALYSTS)
        if invalid:
            raise ValueError(f"Invalid analyst(s): {invalid}. Valid choices: {sorted(VALID_ANALYSTS)}")
        thinking = env_thinking or config.get("google_thinking_level") or "high"

    config["llm_provider"] = env_provider
    config["deep_think_llm"] = os.getenv(
        "TRADINGAGENTS_DEEP_THINK_LLM",
        config.get("deep_think_llm", "gemini-3.1-flash-lite"),
    )
    config["quick_think_llm"] = os.getenv(
        "TRADINGAGENTS_QUICK_THINK_LLM",
        config.get("quick_think_llm", "gemini-3.1-flash-lite"),
    )

    if env_provider == "google":
        config["google_thinking_level"] = thinking
    else:
        config["google_thinking_level"] = None
        config["reasoning_effort"] = os.getenv("TRADINGAGENTS_REASONING_EFFORT", "") or None

    config["backend_url"] = os.getenv("TRADINGAGENTS_LLM_BACKEND_URL") or None
    return analysts, config


@asynccontextmanager
async def _open_robinhood_session():
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

    async with AsyncClient(auth=oauth_provider, follow_redirects=True) as http_client:
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
                yield session, account_number


async def inspect_tax_lot(symbol: str) -> None:
    async with _open_robinhood_session() as (session, account_number):
        rows_by_symbol = await read_live_tax_lots(session, account_number, [symbol.upper()])
        rows = rows_by_symbol.get(symbol.upper(), [])
        print("=" * 72)
        print(f"RAW ROBINHOOD TAX LOTS — {symbol.upper()}")
        print("=" * 72)
        print(json.dumps(rows[:3], indent=2, default=str))
        print()
        print(f"Rows returned: {len(rows)}")


async def read_portfolio_and_run(symbol: str | None = None, mode: str = "fast") -> None:
    total_start = time.perf_counter()

    if LIVE_ORDER_EXECUTION:
        raise RuntimeError("Refusing to start: LIVE_ORDER_EXECUTION must be False.")

    analysts, config = resolve_run_config(mode)

    async with _open_robinhood_session() as (session, account_number):
        portfolio_start = time.perf_counter()
        payload = await read_live_portfolio(session, account_number)
        portfolio = Portfolio.from_robinhood_payload(payload)
        portfolio_elapsed = time.perf_counter() - portfolio_start

        if not portfolio.positions:
            raise RuntimeError("No equity positions were found in the live portfolio.")

        anchor = symbol.upper() if symbol else max(portfolio.positions, key=lambda p: p.market_value).symbol
        known_symbols = {p.symbol for p in portfolio.positions}
        if anchor not in known_symbols:
            raise ValueError(
                f"Anchor symbol {anchor} is not in the live portfolio. Available: {sorted(known_symbols)}"
            )

        context = build_portfolio_context(portfolio)

        graph_start = time.perf_counter()
        graph = TradingAgentsGraph(selected_analysts=analysts, debug=False, config=config)
        graph_init_elapsed = time.perf_counter() - graph_start
        graph.propagator.set_portfolio_context(context)

        print("=" * 72)
        print("TRADINGAGENTS — LIVE ROBINHOOD PORTFOLIO / READ ONLY")
        print("=" * 72)
        print(f"TradingAgents source: {TRADINGAGENTS_ROOT}")
        print(f"Mode:              {mode.upper()}")
        print(f"Analysts:          {', '.join(analysts)}")
        print(f"Provider:          {config['llm_provider']}")
        print(f"Deep-think model:  {config['deep_think_llm']}")
        print(f"Quick-think model: {config['quick_think_llm']}")
        if config["llm_provider"] == "google":
            print(f"Thinking level:    {config['google_thinking_level']}")
        elif config.get("reasoning_effort"):
            print(f"Reasoning effort:  {config['reasoning_effort']}")
        if config.get("backend_url"):
            print(f"Backend URL:       {config['backend_url']}")
        print(f"Debate rounds:     {config['max_debate_rounds']}")
        print(f"Risk rounds:       {config['max_risk_discuss_rounds']}")
        print(f"Portfolio value:   ${portfolio.portfolio_value}")
        print(f"Buying power:      ${portfolio.buying_power}")
        print(f"Research anchor:   {anchor}")
        print(f"Portfolio read:    {portfolio_elapsed:.2f}s")
        print(f"Graph init:        {graph_init_elapsed:.2f}s")
        print()
        print("Running TradingAgents...", flush=True)

        graph_run_start = time.perf_counter()
        _, decision = graph.propagate(anchor, date.today().isoformat(), asset_type="stock")
        graph_run_elapsed = time.perf_counter() - graph_run_start
        total_elapsed = time.perf_counter() - total_start

        print()
        print("=" * 72)
        print("TRADINGAGENTS FINAL PORTFOLIO DECISION")
        print("=" * 72)
        print(decision)
        print()
        print("TIMING")
        print("-" * 72)
        print(f"Portfolio read:    {portfolio_elapsed:.2f}s")
        print(f"Graph init:        {graph_init_elapsed:.2f}s")
        print(f"TradingAgents run: {graph_run_elapsed:.2f}s")
        print(f"Total runtime:     {total_elapsed:.2f}s")
        print()
        print("LIVE ORDER EXECUTION: DISABLED")
        print("=" * 72)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run TradingAgents against the live Robinhood portfolio in read-only mode."
    )
    parser.add_argument("symbol", nargs="?", help="Optional research anchor symbol from the current portfolio.")
    parser.add_argument(
        "--mode",
        choices=("fast", "full"),
        default=os.getenv("TRADINGAGENTS_MODE", "fast"),
        help="Research mode. Fast defaults to market+news and minimal thinking; full uses all four analysts.",
    )
    parser.add_argument(
        "--inspect-tax-lot",
        metavar="SYMBOL",
        help="Print raw Robinhood tax-lot fields instead of running TradingAgents.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.inspect_tax_lot:
        asyncio.run(inspect_tax_lot(args.inspect_tax_lot))
    else:
        selected_symbol = args.symbol.upper() if args.symbol else None
        asyncio.run(read_portfolio_and_run(selected_symbol, args.mode))
