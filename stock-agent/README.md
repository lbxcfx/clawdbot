?# Stock Agent

`stock-agent` is the application-level trading agent layout for this repository.
It is not a single skill.

Recommended boundaries:

- `trading-agent` is the business agent for ETF research, daily sync, signals, and reports.
- `skills/` holds the policy and workflow layer, such as output rules, risk rules, and operator guidance.
- `stock-agent/local-prototype/` holds the current local prototype, reference files, and SQLite schema.
- Over time, the local prototype can be split into clearer services such as market data, strategy, backtest, risk, and execution.

## Layout

- `local-prototype/scripts/stock_agent.py`
  - local prototype CLI
  - covers ETF discovery, universe management, daily sync, top movers, signals, backtests, and trade plans
- `local-prototype/references/`
  - example schema, ETF universe CSV, and example OpenClaw config
- `local-prototype/requirements.txt`
  - Python dependencies for the prototype

## Current Scope

The current prototype is intentionally narrow:

- on-exchange industry ETFs only
- daily bars only
- `strategy-150MA:v1`
- SQLite storage
- paper/live trade-plan generation

It is a local validation path for the trading flow before deeper OpenClaw integration.
