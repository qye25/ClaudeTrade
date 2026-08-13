from __future__ import annotations

from decimal import Decimal
from typing import Any

from portfolio_engine.models import Portfolio
from portfolio_engine.risk_engine import RiskEngine
from portfolio_engine.trade_decision import TradeDecision


def _find_position(
    portfolio: Portfolio,
    symbol: str,
):
    symbol = symbol.upper().strip()

    for position in portfolio.positions:
        if position.symbol.upper() == symbol:
            return position

    return None


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def evaluate_rebalance_decision(
    portfolio: Portfolio,
    decision: TradeDecision,
    projected_portfolio: Portfolio | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Validate an AI-generated trade decision for safe execution.

    IMPORTANT:
    This function does NOT decide whether the investment thesis is good.

    The AI decides:
        BUY / SELL / HOLD
        symbol
        quantity
        confidence
        thesis

    This gate only determines whether the proposed action can safely
    proceed to order review.
    """

    result: dict[str, Any] = {
        "decision": decision.to_dict(),
        "allowed": False,
        "action": None,
        "reasons": [],
        "warnings": [],
    }

    symbol = decision.symbol
    action = decision.action
    quantity = decision.quantity

    # ---------------------------------------------------------
    # HOLD
    # ---------------------------------------------------------

    if action == "HOLD":
        result["allowed"] = True
        result["action"] = "HOLD"
        result["reasons"].append(
            "AI decision is HOLD; no order will be created."
        )
        return result

    # ---------------------------------------------------------
    # Basic validation
    # ---------------------------------------------------------

    if quantity <= 0:
        result["reasons"].append(
            "Trade quantity must be greater than zero."
        )
        return result

    position = _find_position(
        portfolio,
        symbol,
    )

    # ---------------------------------------------------------
    # SELL safety
    # ---------------------------------------------------------

    if action == "SELL":

        if position is None:
            result["reasons"].append(
                f"Cannot SELL {symbol}: no current position exists."
            )
            return result

        current_quantity = _decimal(
            position.quantity
        )

        if quantity > current_quantity:
            result["reasons"].append(
                f"Cannot SELL {quantity} shares of {symbol}; "
                f"current position is only {current_quantity} shares."
            )
            return result

    # ---------------------------------------------------------
    # BUY safety
    # ---------------------------------------------------------

    if action == "BUY":

        if position is None:
            result["warnings"].append(
                f"BUY will create a new position in {symbol}."
            )

        estimated_price = (
            position.last_price
            if position is not None
            else Decimal("0")
        )

        estimated_notional = (
            quantity * estimated_price
        )

        buying_power = _decimal(
            portfolio.buying_power
        )

        # Only perform this check when we have a reliable
        # current price.
        if estimated_price > 0:

            if estimated_notional > buying_power:
                result["reasons"].append(
                    f"Estimated BUY value ${estimated_notional:.2f} "
                    f"exceeds buying power ${buying_power:.2f}."
                )
                return result

    # ---------------------------------------------------------
    # Confidence warning
    # ---------------------------------------------------------

    if decision.confidence < Decimal("0.50"):
        result["warnings"].append(
            "AI confidence is below 0.50."
        )

    # ---------------------------------------------------------
    # Existing portfolio risk is informational.
    #
    # We intentionally DO NOT reject the trade simply because
    # the current portfolio violates the investment policy.
    #
    # Example:
    #
    # UPRO currently = 59.6%
    #
    # AI says:
    # SELL 2 UPRO
    #
    # That trade should be allowed to proceed to the next
    # safety/projection stage even though the current portfolio
    # is already over the desired concentration.
    # ---------------------------------------------------------

    if policy is not None:
        risk_engine = RiskEngine(policy)
        current_risk = risk_engine.evaluate(
            portfolio
        )

        result["current_portfolio_risk"] = current_risk

        if not current_risk.get("allowed", True):
            result["warnings"].append(
                "Current portfolio is outside the configured "
                "investment-risk policy. This is treated as "
                "portfolio state, not as an automatic rejection "
                "of an AI risk-reducing trade."
            )

    # ---------------------------------------------------------
    # Projected portfolio
    # ---------------------------------------------------------

    if projected_portfolio is not None and policy is not None:

        risk_engine = RiskEngine(policy)

        projected_risk = risk_engine.evaluate(
            projected_portfolio
        )

        result["projected_portfolio_risk"] = projected_risk

        current_risk = result.get(
            "current_portfolio_risk"
        )

        if isinstance(current_risk, dict):

            current_leverage = _decimal(
                current_risk.get(
                    "effective_leverage",
                    "0",
                )
            )

            projected_leverage = _decimal(
                projected_risk.get(
                    "effective_leverage",
                    "0",
                )
            )

            if projected_leverage < current_leverage:
                result["reasons"].append(
                    "Projected trade reduces effective portfolio leverage."
                )

            elif projected_leverage > current_leverage:
                result["warnings"].append(
                    "Projected trade increases effective portfolio leverage."
                )

    # ---------------------------------------------------------
    # Passed execution-safety checks
    # ---------------------------------------------------------

    result["allowed"] = True
    result["action"] = "PROPOSED"

    result["reasons"].append(
        "AI decision passed execution-safety validation."
    )

    return result


def evaluate_trade_decision(
    portfolio: Portfolio,
    decision: TradeDecision,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Convenience wrapper for validating an AI TradeDecision.

    No projected portfolio is required.
    """

    return evaluate_rebalance_decision(
        portfolio=portfolio,
        decision=decision,
        projected_portfolio=None,
        policy=policy,
    )