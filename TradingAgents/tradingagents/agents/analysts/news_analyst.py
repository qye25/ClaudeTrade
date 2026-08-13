from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_global_news,
    get_instrument_context_from_state,
    get_language_instruction,
    get_macro_indicators,
    get_news,
    get_prediction_markets,
    get_research_symbols_from_state,
)


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        asset_type = state.get("asset_type", "stock")
        asset_label = "company" if asset_type == "stock" else "asset"
        instrument_context = get_instrument_context_from_state(state)
        research_symbols = get_research_symbols_from_state(state)
        research_context = ", ".join(research_symbols)
        minimal_mode = state.get("minimal_mode", False)

        if minimal_mode:
            symbol = str(state["company_of_interest"]).upper()
            try:
                company_news = get_news.invoke(
                    {"ticker": symbol, "start_date": current_date, "end_date": current_date}
                )
            except Exception as exc:
                company_news = f"Company news unavailable for {symbol}: {exc}"
            try:
                global_news = get_global_news.invoke(
                    {"curr_date": current_date, "look_back_days": 3, "limit": 5}
                )
            except Exception as exc:
                global_news = f"Global news unavailable: {exc}"
            compact_prompt = f"""You are a news researcher supporting a portfolio manager.
Analyze ONLY {symbol} using the supplied recent news evidence plus concise macro context.
Do not request tools and do not invent events.

Instrument context:
{instrument_context}

Company news:
{company_news}

Global/macro news:
{global_news}

Return a compact report covering catalysts, risks, sentiment, and what could materially change the portfolio decision.
""" + get_language_instruction()
            response = llm.invoke(compact_prompt)
            return {
                "messages": [response],
                "news_report": response.content if hasattr(response, "content") else str(response),
            }

        tools = [
            get_news,
            get_global_news,
            get_macro_indicators,
            get_prediction_markets,
        ]

        system_message = (
            f"You are a news researcher supporting a portfolio manager. Analyze recent news and trends over the past week for every selected portfolio holding: {research_context}. "
            f"Use get_news(ticker, start_date, end_date) for {asset_label}-specific news by ticker symbol, and use get_global_news, get_macro_indicators, and get_prediction_markets for broader macro context. "
            "Keep the evidence separated by ticker, identify catalysts and risks, and conclude with a concise cross-portfolio synthesis. "
            "Do not treat the primary anchor as the only asset that matters. Provide specific, actionable insights with supporting evidence."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + get_language_instruction()
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
            "news_report": report,
        }

    return news_analyst_node
