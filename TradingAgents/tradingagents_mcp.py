from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG


PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")

mcp = MCPServer("TradingAgents")


PROVIDERS = {
    "google": {
        "deep": "gemini-3.1-flash-lite",
        "quick": "gemini-3.1-flash-lite",
    },
    "groq": {
        "deep": "llama-3.3-70b-versatile",
        "quick": "llama-3.1-8b-instant",
    },
    "openrouter": {
        "deep": "openrouter/free",
        "quick": "openrouter/free",
    },
}

VALID_ANALYSTS = {"market", "social", "news", "fundamentals"}
FAST_ANALYSTS = ("market", "news")
FULL_ANALYSTS = ("market", "social", "news", "fundamentals")


def _validate_date(value: str, field_name: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD; got {value!r}") from exc
    return value


def _resolve_date_range(
    analysis_date: str | None,
    start_date: str | None,
    end_date: str | None,
) -> tuple[str, str]:
    if analysis_date:
        analysis_date = _validate_date(analysis_date, "analysis_date")
    if start_date:
        start_date = _validate_date(start_date, "start_date")
    if end_date:
        end_date = _validate_date(end_date, "end_date")

    effective_end = end_date or analysis_date or date.today().isoformat()
    effective_end = _validate_date(effective_end, "end_date")
    effective_start = start_date or effective_end
    effective_start = _validate_date(effective_start, "start_date")

    if effective_start > effective_end:
        raise ValueError(
            f"start_date {effective_start} cannot be later than end_date {effective_end}"
        )
    return effective_start, effective_end


def _build_config(provider: str, mode: str, thinking_level: str | None) -> dict:
    provider = provider.lower().strip()
    mode = mode.lower().strip()
    if provider not in PROVIDERS:
        raise ValueError(
            f"Unknown provider '{provider}'. Available providers: {', '.join(PROVIDERS)}"
        )
    if mode not in {"fast", "full"}:
        raise ValueError("mode must be 'fast' or 'full'")

    models = PROVIDERS[provider]
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = provider
    config["deep_think_llm"] = models["deep"]
    config["quick_think_llm"] = models["quick"]

    if provider == "google":
        config["google_thinking_level"] = (
            "minimal" if mode == "fast" else (thinking_level or "high")
        )
    else:
        config["google_thinking_level"] = None
        if thinking_level:
            config["reasoning_effort"] = thinking_level

    if mode == "fast":
        config["google_thinking_level"] = "minimal"
        config["max_debate_rounds"] = 1
        config["max_risk_discuss_rounds"] = 1
    return config


def _resolve_analysts(mode: str, analysts: str | None) -> tuple[str, ...]:
    mode = mode.lower().strip()
    if mode == "fast":
        return FAST_ANALYSTS

    if not analysts:
        return FULL_ANALYSTS

    selected = tuple(
        item.strip().lower()
        for item in analysts.split(",")
        if item.strip()
    )
    invalid = sorted(set(selected) - VALID_ANALYSTS)
    if invalid:
        raise ValueError(
            f"Invalid analyst(s): {invalid}. Valid choices: {sorted(VALID_ANALYSTS)}"
        )
    if not selected:
        raise ValueError("At least one analyst must be selected")
    return selected


def _run_graph(
    *,
    ticker: str,
    analysis_date: str,
    provider: str,
    mode: str,
    analysts: str | None = None,
    thinking_level: str | None = None,
    portfolio_context: str = "",
    research_symbols: tuple[str, ...] = (),
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    ticker = ticker.upper().strip()
    selected_analysts = _resolve_analysts(mode, analysts)
    config = _build_config(provider, mode, thinking_level)
    range_start, range_end = _resolve_date_range(analysis_date, start_date, end_date)

    # Persist the explicit research window in config/context so downstream
    # agents and the Portfolio Manager have the exact requested analysis range.
    config["analysis_start_date"] = range_start
    config["analysis_end_date"] = range_end
    range_note = (
        f"ANALYSIS WINDOW: {range_start} through {range_end}. "
        "Use this exact window when interpreting historical evidence and news."
    )
    if portfolio_context:
        portfolio_context = f"{range_note}\n\n{portfolio_context}"
    else:
        portfolio_context = range_note

    trading_graph = TradingAgentsGraph(
        selected_analysts=selected_analysts,
        debug=False,
        config=config,
    )

    trading_graph.propagator.set_portfolio_context(portfolio_context)
    if research_symbols:
        trading_graph.propagator.set_research_symbols(research_symbols)

    _, decision = trading_graph.propagate(
        ticker,
        range_end,
        asset_type="stock",
    )

    return str(decision)


@mcp.tool()
def analyze_stock(
    ticker: str,
    analysis_date: str | None = None,
    provider: str = "google",
    mode: str = "fast",
    analysts: str | None = None,
    thinking_level: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """
    Run TradingAgents for one research anchor.

    Date range:
    - start_date: first date of the requested evidence window, YYYY-MM-DD.
    - end_date: last date of the requested evidence window, YYYY-MM-DD.
    - analysis_date is retained for backward compatibility and defaults to end_date.

    FAST uses market+news, minimal thinking, and the optimized short graph.
    FULL uses all four analysts by default and honors the requested thinking level.
    """
    try:
        return _run_graph(
            ticker=ticker,
            analysis_date=analysis_date or end_date or date.today().isoformat(),
            provider=provider,
            mode=mode,
            analysts=analysts,
            thinking_level=thinking_level,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as exc:
        return f"TradingAgents analysis failed: {type(exc).__name__}: {exc}"


@mcp.tool()
def analyze_portfolio(
    anchor_ticker: str,
    portfolio: str,
    analysis_date: str | None = None,
    provider: str = "google",
    mode: str = "fast",
    research_symbols: str | None = None,
    analysts: str | None = None,
    thinking_level: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """
    Run a whole-portfolio TradingAgents decision.

    portfolio must be a JSON object/string containing the complete normalized
    portfolio context used by the Portfolio Manager: holdings, weights, cash,
    buying power, leverage, and optional tax-lot information.

    research_symbols is optional and limits the detailed market/news research
    universe; it does not remove other holdings from the Portfolio Manager's
    decision context.

    start_date/end_date define the explicit research window.
    """
    try:
        parsed = json.loads(portfolio)
        portfolio_context = json.dumps(parsed, indent=2, default=str)
    except (TypeError, json.JSONDecodeError) as exc:
        return f"Invalid portfolio JSON: {exc}"

    selected_research = tuple(
        item.strip().upper()
        for item in (research_symbols or "").split(",")
        if item.strip()
    )

    try:
        return _run_graph(
            ticker=anchor_ticker,
            analysis_date=analysis_date or end_date or date.today().isoformat(),
            provider=provider,
            mode=mode,
            analysts=analysts,
            thinking_level=thinking_level,
            portfolio_context=portfolio_context,
            research_symbols=selected_research,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as exc:
        return f"TradingAgents portfolio analysis failed: {type(exc).__name__}: {exc}"


if __name__ == "__main__":
    mcp.run()
