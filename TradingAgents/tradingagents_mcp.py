from pathlib import Path

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG


# Always load the .env next to this MCP server.
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
        "quick": "llama-3.3-70b-versatile",
    },
    "openrouter": {
        "deep": "openrouter/free",
        "quick": "openrouter/free",
    },
}


@mcp.tool()
def analyze_stock(
    ticker: str,
    analysis_date: str,
    provider: str = "google",
) -> str:
    """
    Run a full TradingAgents stock analysis.

    ticker:
        Stock ticker such as NVDA, AAPL, MSFT.

    analysis_date:
        Trading/analysis date in YYYY-MM-DD format.

    provider:
        LLM provider:
        - google
        - groq
        - openrouter

        Defaults to google/Gemini.
    """

    ticker = ticker.upper().strip()
    provider = provider.lower().strip()

    if provider not in PROVIDERS:
        return (
            f"Unknown provider '{provider}'. "
            f"Available providers: {', '.join(PROVIDERS)}"
        )

    models = PROVIDERS[provider]

    config = DEFAULT_CONFIG.copy()

    # Explicitly select the provider and models.
    config["llm_provider"] = provider
    config["deep_think_llm"] = models["deep"]
    config["quick_think_llm"] = models["quick"]

    analysts = (
        "market",
        "social",
        "news",
        "fundamentals",
    )

    trading_graph = TradingAgentsGraph(
        selected_analysts=analysts,
        debug=False,
        config=config,
    )

    _, decision = trading_graph.propagate(
        ticker,
        analysis_date,
        asset_type="stock",
    )

    return str(decision)


if __name__ == "__main__":
    mcp.run()