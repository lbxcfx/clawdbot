---
name: trading-risk-policy
description: Risk policy for the stock trading agent. Use when validating paper/live trade requests, interpreting risk gates, or deciding whether execution is allowed.
---

# Trading Risk Policy

## Hard Stops

Never allow the stock trading agent to bypass these checks:

- latest market data sync must be completed
- target symbol must be in the allowed universe
- strategy must be `strategy-150MA:v1` during phase 1
- live mode requires a recent completed backtest
- live mode requires explicit approval

## Default Behavior

- Default to `paper` when the user does not explicitly request `live`.
- If a precondition is missing, stop and state the missing item.
- If risk data is stale or unavailable, do not infer a pass.

## Required Risk Summary

When returning a plan or execution recommendation, include:

- requested mode
- strategy id and version
- symbol and universe check result
- sync freshness result
- backtest recency result
- final allow/deny decision
- plain-language reason

## Forbidden Behavior

Do not:

- assume approval exists
- assume a backtest is recent enough without evidence
- reinterpret a failed risk gate as a warning
- convert a `paper` request into `live`
