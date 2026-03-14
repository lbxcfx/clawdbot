# Trading Plugin

This plugin exposes the local `stock-agent` prototype to OpenClaw as a single tool:

- tool name: `trading_agent`

## Supported Actions

- `sync_daily`
- `sync_status`
- `strategy_daily_report`
- `top_movers`
- `etf_detail`
- `batch_signal_150ma`

## WSL Ubuntu Notes

- Default Python executable is `python3`
- Point `scriptPath` to `stock-agent/local-prototype/scripts/stock_agent.py`
- Point `dbPath` to the SQLite database used by `trading-agent`

## Example Plugin Config

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
          "scriptPath": "~/openclaw/stock-agent/local-prototype/scripts/stock_agent.py",
          "dbPath": "~/.openclaw/workspace-trading/data/industry.db"
        }
      }
    }
  }
}
```

## Example Tool Calls

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
{ "action": "etf_detail", "symbol": "512170", "recentBars": 10 }
```
