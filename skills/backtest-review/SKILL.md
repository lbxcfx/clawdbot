---
name: backtest-review
description: Review rules for stock strategy backtests. Use when interpreting backtest results, comparing runs, or deciding whether a strategy is fit for paper/live trading.
---

# Backtest Review

## Minimum Review Items

Always check and report:

- strategy id and version
- symbol
- backtest window
- capital
- total return
- annual return
- max drawdown
- win rate
- trade count

## Interpretation Rules

- Separate raw metrics from judgment.
- A profitable backtest is not enough by itself; note drawdown and trade frequency.
- If the sample is too short or trade count is too low, say confidence is limited.
- If the result is being used for `live`, check recency explicitly.

## Output

Return:

- what the backtest proves
- what it does not prove
- whether it is suitable for `paper`
- whether it is eligible for `live`
