from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_indicators,
    get_instrument_context_from_state,
    get_language_instruction,
    get_research_symbols_from_state,
    get_stock_data,
    get_verified_market_snapshot,
)


def _compact_text(value: object, *, max_chars: int = 1800, tail_lines: int = 8) -> str:
    """Keep only the most useful recent evidence for FAST LLM calls."""
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    lines = text.splitlines()
    tail = lines[-tail_lines:]
    compact = "\n".join(tail)
    if len(compact) <= max_chars:
        return "...\n" + compact
    return compact[-max_chars:]


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)
        research_symbols = get_research_symbols_from_state(state)
        research_context = ", ".join(research_symbols)
        minimal_mode = state.get("minimal_mode", False)

        if minimal_mode:
            symbol = str(state["company_of_interest"]).upper()
            lookback_days = 10
            try:
                stock_data = get_stock_data.invoke(
                    {
                        "symbol": symbol,
                        "start_date": current_date,
                        "end_date": current_date,
                    }
                )
            except Exception as exc:
                stock_data = f"Market data unavailable for {symbol}: {exc}"

            try:
                indicator = get_indicators.invoke(
                    {
                        "symbol": symbol,
                        "indicator": "rsi",
                        "curr_date": current_date,
                        "look_back_days": lookback_days,
                    }
                )
            except Exception as exc:
                indicator = f"RSI unavailable: {exc}"

            compact_prompt = f"""You are the Market Analyst for a portfolio manager.
Analyze ONLY {symbol} using the supplied evidence. Be concise and actionable.
Do not request tools and do not invent values.

Instrument: {instrument_context}

Recent OHLCV evidence:
{_compact_text(stock_data, max_chars=1200, tail_lines=6)}

RSI evidence:
{_compact_text(indicator, max_chars=900, tail_lines=6)}

Return a compact report covering trend, momentum, volatility/risk, and the most important opportunity or concern.
"""
            response = llm.invoke(compact_prompt)
            content = getattr(response, "content", None) or str(response)
            return {
                "messages": [response],
                "market_report": content,
            }

        tools = [
            get_stock_data,
            get_indicators,
            get_verified_market_snapshot,
        ]

        system_message = (
            """You are a trading assistant tasked with analyzing financial markets. """
            "The portfolio manager will make one decision for the entire account. "
            "Your job is to research every symbol in the selected research universe, "
            "not just the primary anchor. Use exact tickers in tool calls and clearly "
            "separate evidence for each symbol. "
            f"For each symbol, select no more than 8 complementary technical indicators. "
            "Use concise outputs: do not request unnecessary historical rows. "
            "For technical indicators, use at most 60 calendar days of history. "
            "Categories and indicators:\n\n"
            "Moving Averages: close_50_sma, close_200_sma, close_10_ema.\n"
            "MACD Related: macd, macds, macdh.\n"
            "Momentum: rsi.\n"
            "Volatility: boll, boll_ub, boll_lb, atr.\n"
            "Volume: vwma.\n\n"
            "Use diverse, complementary indicators. Call get_stock_data before get_indicators. "
            "Call get_verified_market_snapshot for each researched ticker before making exact price-level claims. "
            "Do not invent historical validation, support/resistance bounces, or exact percentage moves. "
            "Provide concise but actionable evidence for the portfolio manager."
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant collaborating with a portfolio manager. "
                    "Use the provided tools to progress toward the research task. "
                    "Today's date is {current_date}. {instrument_context}\n"
                    "Primary research anchor: {primary_anchor}\n"
                    "Selected research universe: {research_context}\n"
                    "Research every selected symbol before finishing.\n"
                    "{system_message}"
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        prompt = prompt.partial(primary_anchor=str(state["company_of_interest"]).upper())
        prompt = prompt.partial(research_context=research_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "market_report": report,
        }

    return market_analyst_node
