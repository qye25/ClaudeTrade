# Portfolio Rules

Policy version: 1.0
Date: 2026-08-12
Status: Active

## 1. Portfolio

Target holdings:

| Symbol | Target | Preferred Range | Hard Max |
|---|---:|---:|---:|
| UPRO | 45% | 35–50% | 60% |
| TSLA | 22% | 16–27% | — |
| RKLB | 13% | 9–16% | — |
| NFLX | 10% | 7–13% | — |
| DFEN | 5% | 3–7% | — |

The portfolio is intended to remain concentrated in these five positions unless
the user explicitly approves a change to the policy.

---

## 2. Hard Risk Constraints

These constraints override TradingAgents signals.

### Effective leverage

Calculate:

    effective leverage =
        UPRO weight × 3
      + DFEN weight × 3
      + TSLA weight
      + RKLB weight
      + NFLX weight

Maximum effective leverage:

    200%

A proposed trade must not cause effective leverage to exceed 200%.

If the portfolio is approaching the leverage limit, risk reduction takes
priority over bullish signals.

### UPRO concentration

UPRO:

- Preferred range: 35–50%
- Target: 45%
- Hard maximum: 60%

If UPRO exceeds 50%, do not add to UPRO solely because of a bullish signal.

If UPRO reaches/exceeds the 60% hard maximum, reducing UPRO takes priority
over other portfolio opportunities.

---

## 3. Position Sizing

The preferred objective is to keep positions inside their preferred ranges.

Being below target does not automatically require an immediate trade.

Priority increases when:

1. Position is outside its preferred range.
2. Position is materially below target.
3. There is a confirmed bullish signal.
4. The proposed trade improves portfolio risk/position balance.

Do not trade merely because a signal exists when the position is already
appropriately sized.

---

## 4. Decision Hierarchy

Every rebalance decision must follow this order:

1. Hard risk constraints
2. Effective leverage and concentration
3. Tax impact
4. Trading signal / expected return
5. Transaction efficiency

A lower-priority consideration can never override a higher-priority constraint.

Example:

A bullish UPRO signal does not justify adding UPRO when UPRO is already
above its preferred maximum.

---

## 5. TradingAgents Signals

TradingAgents is a decision-support system, not the final authority.

Signals must be evaluated against the portfolio rules before becoming trades.

### Confirmation rule

For a new/additional position:

- Prefer at least 2 consecutive bullish signals before treating the signal
  as actionable.
- A persistent Overweight signal for 2+ consecutive sessions qualifies as
  confirmed bullish momentum.
- A signal transition such as Overweight → Buy can qualify as actionable
  after the 2-day confirmation threshold when the underlying position is
  materially underweight.
- Stronger confirmation can justify greater confidence, but does not override
  risk constraints.

### Signal persistence

Track consecutive bullish days for each symbol.

Example:

    Overweight → Overweight → Overweight

is stronger confirmation than:

    Overweight → Hold → Buy

The signal history should be retained by the analysis system.

---

## 6. No Signal-Only Trading

Do not trade solely because an agent produces:

- Buy
- Overweight
- Strong Buy
- Bullish
- Positive sentiment

A trade requires a portfolio reason in addition to the signal.

Possible portfolio reasons include:

- correcting an underweight position
- reducing a concentration
- reducing leverage
- restoring a position to its preferred range
- tax-efficient rebalancing

---

## 7. Self-Funded Rebalancing

Rebalancing should be self-funded unless the user explicitly authorizes
additional cash.

Normally:

    sell proceeds >= purchase proceeds

for a rebalance.

Do not introduce new capital merely to satisfy a TradingAgents recommendation.

---

## 8. Trade Limits

Maximum individual trade:

    $150

Minimum individual trade:

    $25

Maximum trades per week:

    4

A multi-leg rebalance counts each buy/sell leg as one trade.

Example:

    Sell UPRO
    Buy RKLB
    Buy NFLX

counts as 3 trades.

---

## 9. Tax-Aware Rebalancing

Tax impact is a secondary constraint, after hard risk and leverage limits.

The system should prefer a tax-efficient way of accomplishing an otherwise
valid rebalance.

When available, use Robinhood tax-lot data rather than average cost alone.

Evaluate:

- acquisition date
- quantity
- cost basis
- unrealized gain/loss
- short-term vs long-term status
- estimated realized gain/loss
- wash-sale considerations
- applicable federal tax considerations
- applicable Washington tax considerations

Tax optimization must never prevent a required hard-risk reduction.

Example:

If UPRO exceeds its hard maximum, UPRO should be reduced even if doing so
creates a taxable gain.

However, when multiple valid lots can satisfy the same risk reduction,
prefer the lot/path with the lower estimated tax impact.

All tax calculations must be deterministic Python calculations rather than
LLM judgments.

Tax output must be labeled:

    Estimated tax impact — not tax advice.

---

## 10. Tax Profile

Current user-provided assumptions:

- Filing status: Single
- Approximate taxable income: $180,000
- State: Washington
- Account type: Taxable brokerage

These values are inputs to the tax-estimation layer.

They must not be sent to TradingAgents/Gemini unless explicitly necessary.

Tax calculations should remain local to the portfolio/risk engine.

---

## 11. Wash-Sale Handling

The system should flag potential wash-sale situations rather than assuming
they are harmless.

Before selling at a loss, check for relevant purchases/re-purchases within
the applicable wash-sale window when sufficient transaction data is available.

If transaction history is incomplete:

    status = "wash-sale check incomplete"

Do not claim that a loss is definitively deductible without sufficient data.

---

## 12. Portfolio Data

Robinhood is the source of truth for live portfolio state.

The read-only adapter should retrieve:

- account
- portfolio value
- buying power
- positions
- quantities
- current quotes
- tax lots when available

Account identifiers must remain internal and must never be sent to the LLM.

---

## 13. Effective Leverage

The normalized portfolio must calculate effective leverage from live weights.

Current leverage model:

    UPRO = 3×
    DFEN = 3×
    TSLA = 1×
    RKLB = 1×
    NFLX = 1×

Effective leverage is calculated before and after every proposed rebalance.

The risk engine must reject any proposal that would exceed:

    200%

---

## 14. Proposed Trade Evaluation

Every proposed trade must pass this sequence:

    Live portfolio
        ↓
    Position normalization
        ↓
    Effective leverage
        ↓
    Hard constraint check
        ↓
    Concentration check
        ↓
    Tax-lot analysis
        ↓
    Signal confirmation
        ↓
    Trade-size / weekly-limit check
        ↓
    Proposed order
        ↓
    User approval

The LLM may recommend.

The deterministic risk engine decides whether the recommendation is permitted.

The user gives final authorization for live execution.

---

## 15. Order Execution

Live order placement is disabled by default.

No agent may:

- place an order
- modify an order
- cancel an order

without passing the deterministic risk gate and receiving explicit user
authorization.

Order review and order placement must remain separate operations.

---

## 16. Market Timing

When the market is closed, proposed trades should be presented as intended
regular-hours orders rather than implying that they have executed.

Never represent a proposed order as filled until Robinhood confirms execution.

---

## 17. Risk Overrides

Hard constraints override all model signals.

Examples:

- UPRO > 60% → reduce UPRO
- effective leverage > 200% → reduce leverage
- proposed trade > $150 → reject
- more than 4 trades/week → reject
- insufficient self-funding → reject

Tax efficiency cannot override a hard risk requirement.

---

## 18. No Automatic Policy Changes

Agents may recommend changes to these portfolio rules.

Agents may not modify this policy automatically.

Any change to:

- targets
- preferred ranges
- hard limits
- leverage assumptions
- trade limits
- tax assumptions
- execution permissions

requires explicit user approval.

Policy changes should be versioned and recorded in CHANGELOG.md.

---

## 19. Current Execution State

Current intended state:

    Robinhood MCP: connected
    Portfolio reads: enabled
    Quotes: enabled
    Tax-lot reads: enabled
    TradingAgents analysis: enabled
    Risk engine: required
    Order review: allowed after risk approval
    Live order placement: disabled until explicitly authorized