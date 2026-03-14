# Stock Agent Local Prototype

This directory is the local prototype used to validate the stock-agent business flow before OpenClaw integration.

## Scope

- industry on-exchange ETFs only
- daily bars only
- `strategy-150MA:v1` only
- SQLite storage
- paper/live trade-plan generation

## Quick Start

```bash
python scripts/stock_agent.py init-db --db ./data/stock-agent.db
python scripts/stock_agent.py discover-industry-etfs --db ./data/stock-agent.db --output ./data/industry-etf-candidates.csv
python scripts/stock_agent.py seed-universe --db ./data/stock-agent.db --csv ./data/industry-etf-candidates.csv
python scripts/stock_agent.py sync-range --db ./data/stock-agent.db --start 2025-03-01 --end 2025-03-11
python scripts/stock_agent.py coverage-report --db ./data/stock-agent.db --start 2025-03-01 --end 2025-03-11
python scripts/stock_agent.py prune-empty-data --db ./data/stock-agent.db --start 2025-03-01 --end 2025-03-11 --csv ./data/industry-etf-candidates.csv
python scripts/stock_agent.py audit-universe --db ./data/stock-agent.db
python scripts/stock_agent.py prune-non-industry --db ./data/stock-agent.db --csv ./data/industry-etf-candidates.csv
python scripts/stock_agent.py sync-range --db ./data/stock-agent.db --start 2024-06-01 --end 2025-03-11
python scripts/stock_agent.py batch-backtest-150ma --db ./data/stock-agent.db --start 2024-10-01 --end 2025-03-11
python scripts/stock_agent.py batch-signal-150ma --db ./data/stock-agent.db --trade-date 2026-03-11
python scripts/stock_agent.py sync-status --db ./data/stock-agent.db
python scripts/stock_agent.py strategy-daily-report --db ./data/stock-agent.db --trade-date 2026-03-11
python scripts/stock_agent.py top-movers --db ./data/stock-agent.db --trade-date 2026-03-11 --top 10
python scripts/stock_agent.py etf-detail --db ./data/stock-agent.db --symbol 512170 --recent-bars 10
python scripts/stock_agent.py strategy-get --db ./data/stock-agent.db
python scripts/stock_agent.py strategy-data-check --db ./data/stock-agent.db --symbol 159611 --purpose backtest --start 2024-06-01 --end 2025-03-11
python scripts/stock_agent.py signal-150ma --db ./data/stock-agent.db --symbol 159999
python scripts/stock_agent.py backtest-150ma --db ./data/stock-agent.db --symbol 159999 --start 2024-01-02 --end 2024-11-05 --report ./data/159999.backtest.json --report-html ./data/159999.backtest.html
python scripts/stock_agent.py trade-plan-150ma --db ./data/stock-agent.db --symbol 159999 --mode paper
```

## Notes

- Basic OpenClaw invocation patterns for `trading-agent`:
  - daily automation: "Run the stock-agent daily sync for the trading database and summarize coverage, top movers, and the strategy daily report."
  - market summary: "Show the latest top movers report for 1-day, 3-day, and 5-day industry ETFs."
  - strategy summary: "Show today's strategy daily report and list all buy and sell candidates."
  - ETF detail: "Show ETF detail for 512170, including the latest bar, recent returns, and current 150MA signal."
- Basic OpenClaw plugin bridge:
  - local extension path: `extensions/trading-plugin`
  - registered tool name: `trading_agent`
  - supported actions: `sync_daily`, `sync_status`, `strategy_daily_report`, `top_movers`, `etf_detail`, `batch_signal_150ma`
  - WSL Ubuntu default: use `python3`
  - before updating OpenClaw, commit or move `stock-agent/`, `extensions/trading-plugin/`, and related `skills/` changes so the trading-agent files are not lost
- `discover-industry-etfs` pulls all on-exchange ETF candidates from AkShare and filters to generic explicit industry ETF names only.
- Pass `--keywords ??,??,??` when you want to narrow the candidate list after the full scan.
- Use `sync-range --start 2025-03-01 --end 2025-03-11` to download the exact March 1, 2025 to March 11, 2025 validation window.
- Use `coverage-report` after `sync-range` to verify which confirmed symbols actually had bars in that window.
- Use `prune-empty-data` to remove symbols that still have no AkShare bars after retries in the requested window.
- Use `audit-universe` to detect symbols that are likely not pure industry ETFs and should be excluded from the strategy universe.
- Use `prune-non-industry` to remove those flagged symbols from both the current universe and the candidate CSV.
- Download at least 150 trading days of history before running real `strategy-150MA` backtests or signals.
- Use `strategy-data-check` before backtests or signals when you want a reusable precheck for strategy data sufficiency.
- Strategy data insufficiency now returns a structured `strategy_data_check` report and batch jobs mark those symbols as `skipped`, not `failed`.
- Daily production sync should run at `16:00` local market time after the trading session closes.
- `sync-daily` now backfills from each symbol's latest stored trade date up to the target date, so it can recover automatically after several missed trading days.
- `sync-daily` reports `gap_days` and `backfilled` per symbol, plus aggregate `backfilled_symbols` and `total_gap_days`.
- `sync-daily` also returns `coverage_summary` for the target trade date, so the daily job can immediately verify whether the candidate universe is fully covered for that day.
- `sync-daily` now also returns `top_movers`, which contains the top 10 ETFs ranked by 1-day, 3-day, and 5-day percentage gain for the target trade date.
- `sync-daily` now also returns `strategy_daily_report`, which groups the target trade date's `buy` and `sell` candidates after the data update completes.
- `sync-status` now includes the latest sync run's `coverage_summary` too, so monitoring can read one command and know whether the latest trade date is fully covered.
- Use `strategy-daily-report` when you want a standalone strategy summary for a specific trade date, including `buy_list`, `sell_list`, and skipped symbols with data insufficiency reasons.
- Use `top-movers` when you want the latest or a specific trade date's 1d/3d/5d top-10 ETF gainers without rerunning sync.
- Use `etf-detail` for interactive page lookup of a specific ETF, including latest OHLCV, recent bars, short-horizon returns, and the latest 150MA signal when available.
- Market-data downloads now retry transient AkShare failures automatically.
- If retries still end with `empty_data`, treat that as likely source-side unavailable data for the requested symbol/date window.
- `seed-demo-bars` is the offline validation path. It writes deterministic bars and records a completed `sync_daily` run by default.
- `--trend bullish` is useful for backtest validation.
- `--trend signal-buy` or `--trend signal-sell` is useful for validating the final-day signal and trade-plan path.
- Use AkShare commands only when validating online sync behavior.
- `report-html` falls back to a basic HTML report if `pyecharts` is not installed.
