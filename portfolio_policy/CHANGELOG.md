# Portfolio Policy Changelog

## 2026-08-12 — v1.0

Initial policy established.

### Portfolio
- UPRO target 45%, preferred range 35–50%, hard max 60%
- TSLA target 22%, preferred range 16–27%
- RKLB target 13%, preferred range 9–16%
- NFLX target 10%, preferred range 7–13%
- DFEN target 5%, preferred range 3–7%

### Risk
- Effective leverage maximum: 200%
- Individual trade maximum: $150
- Individual trade minimum: $25
- Maximum 4 trades/week
- Self-funded rebalancing by default

### Decision hierarchy
1. Hard risk limits
2. Leverage/concentration
3. Tax impact
4. Trading signal
5. Transaction efficiency

### Tax
- Tax-aware rebalancing enabled conceptually
- Robinhood tax-lot data preferred over average-cost fallback
- Tax calculations remain deterministic
- Wash-sale checking required where data permits
- Tax output labeled "Estimated tax impact — not tax advice."

### Execution
- Robinhood read access enabled
- Tax-lot read access being validated
- Order placement remains disabled
- Policy changes require explicit user approval