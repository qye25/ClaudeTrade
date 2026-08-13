"""Portfolio Manager: synthesises the risk-analyst debate into the final decision."""

from __future__ import annotations

from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    NO_EXTERNAL_TOOLS,
    bind_structured,
    invoke_structured_or_freetext,
)


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]
        portfolio_context = state.get("portfolio_context", "")

        past_context = state.get("past_context", "")
        lessons_line = (
            f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            if past_context
            else ""
        )

        portfolio_line = (
            f"\n**CURRENT PORTFOLIO (PRIMARY DECISION CONTEXT):**\n"
            f"{portfolio_context}\n"
            if portfolio_context
            else "\n**CURRENT PORTFOLIO:** unavailable\n"
        )

        prompt = f"""As the Portfolio Manager, synthesize the research and risk debate into the final AI-native trading decision.

The instrument below is the research anchor. The final decision must consider the ENTIRE portfolio, not just the anchor instrument.

{instrument_context}
{portfolio_line}
---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to the portfolio exposure
- **Overweight**: Favorable outlook; increase portfolio exposure gradually
- **Hold**: Maintain exposure; no immediate portfolio action
- **Underweight**: Reduce exposure or trim concentration
- **Sell**: Exit the exposure

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
{lessons_line}
**Risk Analysts Debate History:**
{history}

---

Portfolio decision requirements:
1. Evaluate concentration, leverage, liquidity, and current exposure across the whole account.
2. Identify the most important portfolio-level risk or opportunity before choosing the rating.
3. Do not assume an existing position must be held.
4. When recommending a change, explain the portfolio-level reason in complete sentences.
5. Do not claim that a trade is feasible merely because it is desirable; distinguish investment judgment from execution feasibility.

Be decisive and ground every conclusion in specific evidence from the analysts and the portfolio context.

{NO_EXTERNAL_TOOLS}{get_language_instruction()}"""

        final_trade_decision = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_pm_decision,
            "Portfolio Manager",
        )

        new_risk_debate_state = {
            "judge_decision": final_trade_decision,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Portfolio Manager",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_trade_decision,
        }

    return portfolio_manager_node
