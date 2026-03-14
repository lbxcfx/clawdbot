# Trading Plugin

这个插件把 `trading-agent` 正式运行时暴露给 OpenClaw，统一作为一个工具使用：

- 工具名：`trading_agent`

## 支持动作

- `sync_daily`
- `sync_status`
- `strategy_daily_report`
- `top_movers`
- `search_etf`
- `etf_detail`
- `technical_indicators`
- `technical_analysis`
- `batch_signal_150ma`

## WSL Ubuntu 说明

- 默认 Python 可执行文件是 `python3`
- `scriptPath` 应指向 `stock-agent/trading-agent/scripts/stock_agent.py`
- `dbPath` 指向 `trading-agent` 使用的 SQLite 数据库
- 如果 `dbPath` 不存在，会先从 `bundledDbPath` 复制数据库
- 如果数据库交易池为空，会用 `seedCsvPath` 自动导入候选 ETF CSV

## 示例配置

```json
{
  "plugins": {
    "enabled": true,
    "allow": ["trading-plugin"],
    "load": {
      "paths": ["~/openclaw/extensions/trading-plugin"]
    },
    "entries": {
      "trading-plugin": {
        "enabled": true,
        "config": {
          "pythonBin": "python3",
          "scriptPath": "~/openclaw/stock-agent/trading-agent/scripts/stock_agent.py",
          "dbPath": "~/.openclaw/workspace-trading/data/industry.db",
          "bundledDbPath": "~/openclaw/stock-agent/trading-agent/data/industry.db",
          "seedCsvPath": "~/openclaw/stock-agent/trading-agent/data/industry-etf-candidates.csv"
        }
      }
    }
  }
}
```

## 示例工具调用

```json
{ "action": "sync_status" }
```

```json
{ "action": "strategy_daily_report", "tradeDate": "2026-03-12" }
```

```json
{ "action": "top_movers", "tradeDate": "2026-03-12", "top": 10 }
```

```json
{ "action": "search_etf", "query": "电池ETF", "limit": 10 }
```

```json
{ "action": "etf_detail", "symbol": "512170", "recentBars": 10 }
```

```json
{ "action": "technical_indicators", "symbol": "512170", "recentBars": 10 }
```

```json
{ "action": "technical_analysis", "symbol": "512170", "recentBars": 10, "includeSeries": true }
```
