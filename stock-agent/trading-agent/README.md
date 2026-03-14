# Trading Agent Runtime

这个目录是 `trading-agent` 的正式运行资产目录，已经不再作为 `local-prototype` 使用。

## 范围

- 仅支持场内行业 ETF
- 仅支持日线
- 仅支持 `strategy-150MA:v1`
- 技术分析能力与策略实现解耦
- 使用 SQLite 存储
- 支持模拟/实盘交易计划生成

## 快速开始

```bash
python scripts/stock_agent.py bootstrap-db --db ./data/industry.db --csv ./data/industry-etf-candidates.csv
python scripts/stock_agent.py discover-industry-etfs --db ./data/industry.db --output ./data/industry-etf-candidates.csv
python scripts/stock_agent.py seed-universe --db ./data/industry.db --csv ./data/industry-etf-candidates.csv
python scripts/stock_agent.py search-etf --db ./data/industry.db --query 电池ETF --limit 10
python scripts/stock_agent.py sync-range --db ./data/industry.db --start 2025-03-01 --end 2025-03-11
python scripts/stock_agent.py coverage-report --db ./data/industry.db --start 2025-03-01 --end 2025-03-11
python scripts/stock_agent.py prune-empty-data --db ./data/industry.db --start 2025-03-01 --end 2025-03-11 --csv ./data/industry-etf-candidates.csv
python scripts/stock_agent.py audit-universe --db ./data/industry.db
python scripts/stock_agent.py prune-non-industry --db ./data/industry.db --csv ./data/industry-etf-candidates.csv
python scripts/stock_agent.py batch-backtest-150ma --db ./data/industry.db --start 2024-10-01 --end 2025-03-11
python scripts/stock_agent.py batch-signal-150ma --db ./data/industry.db --trade-date 2026-03-11
python scripts/stock_agent.py sync-status --db ./data/industry.db
python scripts/stock_agent.py strategy-daily-report --db ./data/industry.db --trade-date 2026-03-11
python scripts/stock_agent.py top-movers --db ./data/industry.db --trade-date 2026-03-11 --top 10
python scripts/stock_agent.py latest-price --db ./data/industry.db --symbol 159611
python scripts/stock_agent.py etf-detail --db ./data/industry.db --symbol 512170 --recent-bars 10
python scripts/stock_agent.py technical-indicators --db ./data/industry.db --symbol 512170 --recent-bars 10
python scripts/stock_agent.py technical-analysis --db ./data/industry.db --symbol 512170 --recent-bars 10 --include-series
```

## 说明

- OpenClaw 中 `trading-agent` 的常见调用方式：
  - 日常自动化：`运行 trading-agent 的日常同步，并总结 coverage_summary、top_movers 和 strategy_daily_report。`
  - 市场摘要：`给我最新的行业 ETF 1 日、3 日、5 日涨幅榜。`
  - 策略摘要：`给我今天的策略日报，并列出买入和卖出候选。`
  - 模糊查询：`查一下电池ETF有哪些，并告诉我最新价格。`
  - ETF 详情：`查看 512170 的 ETF 详情，包括最新 K 线、近期收益、技术指标摘要和 150MA 信号。`
  - 技术分析：`查看 512170 的技术指标摘要，重点看 MA、MACD、RSI 和 ADX。`
- 新 agent 开发方法：
  - 参见 `AGENT_DEVELOPMENT.md`
  - 该文档说明如何组织 workspace、skills、runtime、工具契约和测试方法
- 插件收口说明：
  - 插件路径：`extensions/trading-plugin`
  - 工具名：`trading_agent`
  - 支持动作：`sync_daily`、`sync_status`、`strategy_daily_report`、`top_movers`、`search_etf`、`latest_price`、`etf_detail`、`batch_signal_150ma`
  - WSL Ubuntu 默认 Python：`python3`
  - 插件执行前会自动运行 `bootstrap-db`
- `discover-industry-etfs` 会从 AkShare 拉取 ETF 候选，并过滤为显式行业 ETF。
- 当数据库不存在时，插件会先复制内置 `industry.db`，保证基础数据随服务一起可用。
- 当数据库交易池为空时，插件会自动导入 `industry-etf-candidates.csv`。
- `search-etf` 用于按中文名称、板块词或代码检索 ETF，优先解决自然语言到 symbol 的映射问题。
- `latest-price` 只返回最新交易日和最新收盘价，适合“最新价格是多少”这类轻量问题。
- `sync-daily` 会返回 `coverage_summary`、`top_movers` 和 `strategy_daily_report`。
- `sync-status` 会返回最近一次同步状态和覆盖率摘要。
- `technical-indicators` 返回最新一笔技术指标快照，适合策略前的快速检查。
- `technical-analysis` 返回标准化技术分析结果，可附带最近若干条技术指标序列。
- `etf-detail` 会返回最新 K 线、近期收益、最近窗口 K 线、技术指标摘要和最新 150MA 信号，适合需要完整详情时使用。
