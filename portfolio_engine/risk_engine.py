from __future__ import annotations

from decimal import Decimal
from typing import Any

from .models import Portfolio


class RiskEngine:
    def __init__(self, policy: dict[str, Any]):
        self.policy = policy
        self.hard_limits = policy.get("hard_risk_limits", {}) if isinstance(policy, dict) else {}

    def evaluate(self, portfolio: Portfolio) -> dict[str, Any]:
        reasons: list[str] = []
        violations: list[str] = []

        total_effective_leverage = portfolio.total_effective_leverage
        max_leverage = Decimal(str(self.hard_limits.get("max_portfolio_leverage", "999")))
        if total_effective_leverage > max_leverage:
            violations.append("max_portfolio_leverage")
            reasons.append(
                f"Portfolio effective leverage {total_effective_leverage} exceeds hard limit {max_leverage}."
            )

        max_single_weight = Decimal(str(self.hard_limits.get("max_single_position_weight", "1")))
        for position in portfolio.positions:
            if position.weight > max_single_weight:
                violations.append(f"max_single_position_weight:{position.symbol}")
                reasons.append(
                    f"Position {position.symbol} weight {position.weight} exceeds maximum single-position weight {max_single_weight}."
                )

        max_leveraged_etf_weight = Decimal(str(self.hard_limits.get("max_leveraged_etf_weight", "1")))
        for position in portfolio.positions:
            if position.effective_leverage_multiplier > Decimal("1") and position.weight > max_leveraged_etf_weight:
                violations.append(f"max_leveraged_etf_weight:{position.symbol}")
                reasons.append(
                    f"Leveraged ETF {position.symbol} weight {position.weight} exceeds leveraged-ETF cap {max_leveraged_etf_weight}."
                )

        max_total_leveraged_exposure = Decimal(str(self.hard_limits.get("max_total_leveraged_exposure", "999")))
        if total_effective_leverage > max_total_leveraged_exposure:
            violations.append("max_total_leveraged_exposure")
            reasons.append(
                f"Total leveraged exposure {total_effective_leverage} exceeds cap {max_total_leveraged_exposure}."
            )

        allowed = not violations
        return {
            "allowed": allowed,
            "effective_leverage": total_effective_leverage,
            "violations": violations,
            "reasons": reasons,
        }
