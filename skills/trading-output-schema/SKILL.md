---
name: trading-output-schema
description: Output schema rules for the stock trading agent. Use when summarizing sync, strategy, backtest, signal, trade-plan, or execution results.
---

# Trading Output Schema

Prefer structured JSON-shaped summaries over prose-only answers.

## Expected Result Kinds

- `sync_report`
- `sync_status`
- `strategy_report`
- `strategy_daily_report`
- `signal_report`
- `backtest_report`
- `top_movers_report`
- `etf_detail`
- `trade_plan`
- `execution_result`

## Required Envelope

When summarizing tool output, preserve:

- `kind`
- `strategy_id`
- `version`
- `symbol`
- `trade_date` or date range
- `status`

## Trade Plan Minimum Fields

- `kind`
- `plan_id`
- `strategy_id`
- `version`
- `symbol`
- `trade_mode`
- `signal_date`
- `action`
- `target_position`
- `status`
- `rationale`

## Reporting Rule

- Summarize the returned business result.
- Do not invent fields that the tool did not produce.
- If a required field is missing, say it is missing.
