        context = build_portfolio_context(portfolio)

        graph_start = time.perf_counter()
        graph = TradingAgentsGraph(selected_analysts=analysts, debug=False, config=config)
        graph_init_elapsed = time.perf_counter() - graph_start
        graph.propagator.set_portfolio_context(context)
        graph.propagator.set_minimal_mode(mode.lower() == "fast")

        planner_start = time.perf_counter()
        try:
            default_research_limit = 1 if (mode.lower() == "fast" and config["llm_provider"] == "groq") else 3
            research_limit = max(
                1,
                min(
                    5,
                    int(os.getenv("TRADINGAGENTS_RESEARCH_SYMBOL_LIMIT", str(default_research_limit))),
                ),
            )
        except ValueError:
            research_limit = 1 if (mode.lower() == "fast" and config["llm_provider"] == "groq") else 3
        research_symbols, planner_reason = choose_research_symbols(
            graph,
            portfolio,
            limit=research_limit,
        )
        planner_elapsed = time.perf_counter() - planner_start
        if anchor not in research_symbols:
            research_symbols = (anchor,) + tuple(
                symbol_value for symbol_value in research_symbols if symbol_value != anchor
            )[: max(0, research_limit - 1)]
            planner_reason = f"Anchor {anchor} included; {planner_reason}"
        graph.propagator.set_research_symbols(research_symbols)

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
        print(f"Primary anchor:    {anchor}")
        print(f"Research universe: {', '.join(research_symbols)}" )