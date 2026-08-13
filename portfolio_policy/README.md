# Portfolio Policy

This directory stores the deterministic portfolio policy used by the Robinhood read-only adapter and the downstream rebalance/risk engine.

The policy is intentionally separate from the Robinhood OAuth state, account identifiers, and any TradingAgents prompt content. Nothing in this directory should contain account numbers, credentials, or tokens.

## Principles

1. Hard risk limits come first.
2. Leverage and concentration are checked before signal quality.
3. Tax impact is a secondary constraint, not the primary objective.
4. TradingAgents may propose opportunities, but Python policy decides whether the change is allowed.
5. Live order execution remains disabled.

## Policy priority

1. Hard risk limits
2. Leverage / concentration
3. Tax impact
4. Signal / expected return
5. Transaction efficiency

A tax benefit can never justify a violation of a hard risk limit.

## Architecture

Robinhood MCP -> Portfolio Normalizer -> Deterministic Risk Engine -> TradingAgents analysis -> Proposed rebalance -> Risk + tax re-check -> Order review -> LIVE EXECUTION OFF

## Read-only allowlist

The Robinhood adapter must allow only:

- get_accounts
- get_portfolio
- get_equity_positions
- get_equity_quotes
- get_equity_tax_lots
- get_equity_tradability

No order or trade execution tools are enabled.

## Output contract

The portfolio normalizer should emit normalized portfolio state including:

- symbol
- position value
- position weight
- effective leverage contribution
- concentration tier
- lot data
- current price/quote status
- tax lot metadata

The final output passed to any LLM should exclude account numbers and raw identifiers wherever possible.

## Tax note

Tax estimates in this policy are deterministic modeling values only and must be labeled:

> Estimated tax impact — not tax advice.
