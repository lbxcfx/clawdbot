from __future__ import annotations

import math
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from technical_analysis import build_technical_dataframe


@dataclass(frozen=True)
class Strategy150maDeps:
    strategy_id: str
    strategy_version: str
    ensure_symbol_allowed: Callable[[sqlite3.Connection, str], Any]
    get_strategy_requirements: Callable[[sqlite3.Connection, str, str], dict[str, Any]]
    get_strategy_policy: Callable[[sqlite3.Connection], Any]
    list_universe_symbols: Callable[[sqlite3.Connection], list[dict[str, Any]]]
    load_symbol_bars: Callable[..., Any]
    maybe_render_backtest_html: Callable[[dict[str, Any], str | None], str | None]
    require_latest_sync: Callable[[sqlite3.Connection, str], dict[str, Any]]
    require_recent_backtest: Callable[[sqlite3.Connection, str, str], dict[str, Any]]
    utc_now: Callable[[], str]


def max_drawdown(values: list[float]) -> float:
    peak = -math.inf
    max_dd = 0.0
    for value in values:
        peak = max(peak, value)
        if peak <= 0:
            continue
        dd = (peak - value) / peak
        max_dd = max(max_dd, dd)
    return max_dd


def _build_signal_dataframe(conn: sqlite3.Connection, deps: Strategy150maDeps, symbol: str, trade_date: str | None = None):
    df = deps.load_symbol_bars(conn, symbol, end_date=trade_date)
    return build_technical_dataframe(df, indicator_set=["ma"])


def _build_backtest_dataframe(
    conn: sqlite3.Connection,
    deps: Strategy150maDeps,
    symbol: str,
    start_date: str,
    end_date: str,
):
    df = deps.load_symbol_bars(conn, symbol, start_date=start_date, end_date=end_date)
    return build_technical_dataframe(df, indicator_set=["ma"])


def build_strategy_data_check(
    conn: sqlite3.Connection,
    deps: Strategy150maDeps,
    symbol: str,
    purpose: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    if purpose not in {"signal", "backtest"}:
        raise RuntimeError(f"Unsupported strategy data-check purpose: {purpose}")
    member = deps.ensure_symbol_allowed(conn, symbol)
    requirements = deps.get_strategy_requirements(conn, deps.strategy_id, deps.strategy_version)
    purpose_requirements = requirements[purpose]
    df = deps.load_symbol_bars(conn, symbol, start_date=start_date, end_date=end_date)
    row_count = len(df)
    warmup_bars = int(purpose_requirements["warmup_bars"])
    post_warmup_bars = max(0, row_count - warmup_bars)
    first_trade_date = df.iloc[0]["trade_date"].strftime("%Y-%m-%d") if row_count else None
    last_trade_date = df.iloc[-1]["trade_date"].strftime("%Y-%m-%d") if row_count else None
    eligible = row_count >= int(purpose_requirements["min_total_bars"]) and post_warmup_bars >= int(
        purpose_requirements["min_post_warmup_bars"]
    )

    missing_reasons: list[str] = []
    if row_count < int(purpose_requirements["min_total_bars"]):
        missing_reasons.append(
            f"总K线数量不足，需要至少 {purpose_requirements['min_total_bars']} 条，当前仅有 {row_count} 条。"
        )
    if post_warmup_bars < int(purpose_requirements["min_post_warmup_bars"]):
        missing_reasons.append(
            f"预热后可用K线不足，需要至少 {purpose_requirements['min_post_warmup_bars']} 条，当前仅有 {post_warmup_bars} 条。"
        )

    return {
        "kind": "strategy_data_check",
        "strategy_id": deps.strategy_id,
        "version": deps.strategy_version,
        "symbol": symbol,
        "name": member["name"],
        "sector_name": member["sector_name"],
        "purpose": purpose,
        "status": "ready" if eligible else "insufficient_data",
        "eligible": eligible,
        "window": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "available": {
            "total_bars": row_count,
            "post_warmup_bars": post_warmup_bars,
            "first_trade_date": first_trade_date,
            "last_trade_date": last_trade_date,
        },
        "required": {
            "warmup_bars": warmup_bars,
            "min_total_bars": int(purpose_requirements["min_total_bars"]),
            "min_post_warmup_bars": int(purpose_requirements["min_post_warmup_bars"]),
        },
        "message": "数据满足策略要求，可以继续执行。" if eligible else "策略所需历史数据不足，已跳过执行。",
        "missing_reasons": missing_reasons,
    }


def compute_signal_150ma(
    conn: sqlite3.Connection,
    deps: Strategy150maDeps,
    symbol: str,
    trade_date: str | None = None,
) -> dict[str, Any]:
    member = deps.ensure_symbol_allowed(conn, symbol)
    data_check = build_strategy_data_check(conn, deps, symbol=symbol, purpose="signal", end_date=trade_date)
    if not data_check["eligible"]:
        return data_check
    df = _build_signal_dataframe(conn, deps, symbol=symbol, trade_date=trade_date)
    df = df.dropna(subset=["ma_150"]).reset_index(drop=True)
    if len(df) < 2:
        return {
            **data_check,
            "status": "insufficient_data",
            "eligible": False,
            "message": "策略所需历史数据不足，无法计算信号。",
            "missing_reasons": ["预热后可用K线不足，无法完成最近一次穿越判断。"],
        }

    prev_row = df.iloc[-2]
    last_row = df.iloc[-1]
    crossed_up = prev_row["close"] <= prev_row["ma_150"] and last_row["close"] > last_row["ma_150"]
    crossed_down = prev_row["close"] >= prev_row["ma_150"] and last_row["close"] < last_row["ma_150"]
    action = "hold"
    target_position = 0.0
    rationale = "收盘价与150MA未发生穿越。"
    if crossed_up:
        action = "buy"
        target_position = 1.0
        rationale = "收盘价向上突破150日均线，目标仓位100%。"
    elif crossed_down:
        action = "sell"
        target_position = 0.0
        rationale = "收盘价跌破150日均线，目标仓位0%。"

    return {
        "kind": "signal_report",
        "strategy_id": deps.strategy_id,
        "version": deps.strategy_version,
        "symbol": symbol,
        "name": member["name"],
        "sector_name": member["sector_name"],
        "trade_date": last_row["trade_date"].strftime("%Y-%m-%d"),
        "close": float(last_row["close"]),
        "ma150": float(last_row["ma_150"]),
        "action": action,
        "target_position": target_position,
        "rationale": rationale,
    }


def run_backtest_150ma(
    conn: sqlite3.Connection,
    deps: Strategy150maDeps,
    symbol: str,
    start_date: str,
    end_date: str,
    capital: float,
    report_path: str | None,
    report_html: str | None,
) -> dict[str, Any]:
    member = deps.ensure_symbol_allowed(conn, symbol)
    data_check = build_strategy_data_check(
        conn,
        deps,
        symbol=symbol,
        purpose="backtest",
        start_date=start_date,
        end_date=end_date,
    )
    if not data_check["eligible"]:
        return data_check
    df = _build_backtest_dataframe(conn, deps, symbol=symbol, start_date=start_date, end_date=end_date)
    df = df.dropna(subset=["ma_150"]).reset_index(drop=True)
    if len(df) < 3:
        return {
            **data_check,
            "status": "insufficient_data",
            "eligible": False,
            "message": "策略所需历史数据不足，无法完成回测。",
            "missing_reasons": ["预热后可用K线不足，无法完成回测交易路径。"],
        }

    cash = capital
    shares = 0.0
    equity_curve: list[float] = []
    equity_points: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    last_buy_price: float | None = None
    winning_trades = 0

    for idx in range(1, len(df) - 1):
        prev_row = df.iloc[idx - 1]
        row = df.iloc[idx]
        next_row = df.iloc[idx + 1]

        crossed_up = prev_row["close"] <= prev_row["ma_150"] and row["close"] > row["ma_150"]
        crossed_down = prev_row["close"] >= prev_row["ma_150"] and row["close"] < row["ma_150"]

        if shares == 0 and crossed_up:
            next_open = float(next_row["open"])
            if next_open > 0:
                shares = cash / next_open
                cash = 0.0
                last_buy_price = next_open
                trades.append({"date": next_row["trade_date"].strftime("%Y-%m-%d"), "action": "buy", "price": next_open})
        elif shares > 0 and crossed_down:
            next_open = float(next_row["open"])
            cash = shares * next_open
            if last_buy_price is not None and next_open > last_buy_price:
                winning_trades += 1
            shares = 0.0
            last_buy_price = None
            trades.append({"date": next_row["trade_date"].strftime("%Y-%m-%d"), "action": "sell", "price": next_open})

        equity_value = cash + shares * float(row["close"])
        equity_curve.append(equity_value)
        equity_points.append(
            {
                "trade_date": row["trade_date"].strftime("%Y-%m-%d"),
                "close": float(row["close"]),
                "ma150": float(row["ma_150"]),
                "equity": equity_value,
            }
        )

    final_close = float(df.iloc[-1]["close"])
    end_value = cash + shares * final_close
    total_return = (end_value - capital) / capital if capital else 0.0
    trading_days = max(len(df), 1)
    annual_return = (end_value / capital) ** (252 / trading_days) - 1 if capital and end_value > 0 else 0.0
    completed_trades = sum(1 for trade in trades if trade["action"] == "sell")
    win_rate = (winning_trades / completed_trades) if completed_trades else 0.0
    drawdown = max_drawdown(equity_curve) if equity_curve else 0.0

    report = {
        "kind": "backtest_report",
        "strategy_id": deps.strategy_id,
        "version": deps.strategy_version,
        "symbol": symbol,
        "name": member["name"],
        "sector_name": member["sector_name"],
        "start_date": start_date,
        "end_date": end_date,
        "capital": capital,
        "total_return": total_return,
        "annual_return": annual_return,
        "max_drawdown": drawdown,
        "win_rate": win_rate,
        "trade_count": completed_trades,
        "trades": trades,
        "equity_curve": equity_points,
    }

    if report_path:
        from pathlib import Path
        import json

        output_path = Path(report_path).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_path"] = str(output_path)
    if report_html:
        html_path = deps.maybe_render_backtest_html(report, report_html)
        if html_path:
            report["report_html"] = html_path

    run_id = str(uuid.uuid4())
    conn.execute(
        """
        insert into strategy_backtest_runs
        (run_id, strategy_id, version, symbol, start_date, end_date, total_return, annual_return, max_drawdown, win_rate, trade_count, report_path, status, created_at)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            deps.strategy_id,
            deps.strategy_version,
            symbol,
            start_date,
            end_date,
            total_return,
            annual_return,
            drawdown,
            win_rate,
            completed_trades,
            report.get("report_path"),
            "completed",
            deps.utc_now(),
        ),
    )
    conn.commit()
    report["run_id"] = run_id
    return report


def create_trade_plan(conn: sqlite3.Connection, deps: Strategy150maDeps, symbol: str, mode: str) -> dict[str, Any]:
    if mode not in {"paper", "live"}:
        raise RuntimeError("trade mode must be 'paper' or 'live'.")
    policy = deps.get_strategy_policy(conn)
    signal = compute_signal_150ma(conn, deps, symbol)
    if signal["kind"] != "signal_report":
        return {
            "kind": "trade_plan_precheck",
            "strategy_id": deps.strategy_id,
            "version": deps.strategy_version,
            "symbol": symbol,
            "trade_mode": mode,
            "status": "blocked",
            "reason": "insufficient_data",
            "data_check": signal,
        }
    sync_status: dict[str, Any] | None = None
    latest_backtest: dict[str, Any] | None = None
    if bool(policy["require_latest_sync"]):
        sync_status = deps.require_latest_sync(conn, symbol)
    if mode == "live" and bool(policy["require_recent_backtest_for_live"]):
        latest_backtest = deps.require_recent_backtest(conn, symbol, signal_trade_date=str(signal["trade_date"]))
    plan_id = str(uuid.uuid4())
    rationale = signal["rationale"]
    if mode == "live":
        rationale = rationale + " live 模式需要人工审批。"
    conn.execute(
        """
        insert into trading_trade_plans
        (plan_id, strategy_id, version, symbol, trade_mode, signal_date, action, target_position, rationale, status, created_at)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            plan_id,
            deps.strategy_id,
            deps.strategy_version,
            symbol,
            mode,
            signal["trade_date"],
            signal["action"],
            signal["target_position"],
            rationale,
            "pending",
            deps.utc_now(),
        ),
    )
    conn.commit()
    return {
        "kind": "trade_plan",
        "plan_id": plan_id,
        "strategy_id": deps.strategy_id,
        "version": deps.strategy_version,
        "symbol": symbol,
        "trade_mode": mode,
        "signal_date": signal["trade_date"],
        "action": signal["action"],
        "target_position": signal["target_position"],
        "rationale": rationale,
        "status": "pending",
        "sync_status": sync_status,
        "latest_backtest": latest_backtest,
    }


def batch_signal_150ma(conn: sqlite3.Connection, deps: Strategy150maDeps, trade_date: str | None = None) -> dict[str, Any]:
    symbols = deps.list_universe_symbols(conn)
    results: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for item in symbols:
        try:
            signal = compute_signal_150ma(conn, deps, item["symbol"], trade_date=trade_date)
            if signal["kind"] == "signal_report":
                results.append(signal)
            else:
                skipped.append(signal)
        except Exception as exc:
            failed.append({"symbol": item["symbol"], "message": str(exc)})
    action_counts = {
        "buy": sum(1 for row in results if row["action"] == "buy"),
        "sell": sum(1 for row in results if row["action"] == "sell"),
        "hold": sum(1 for row in results if row["action"] == "hold"),
    }
    return {
        "kind": "batch_signal_report",
        "trade_date": trade_date or (results[0]["trade_date"] if results else None),
        "total_symbols": len(symbols),
        "success_symbols": len(results),
        "skipped_symbols": len(skipped),
        "failed_symbols": len(failed),
        "action_counts": action_counts,
        "signals": results,
        "skipped": skipped,
        "failures": failed,
    }


def batch_backtest_150ma(
    conn: sqlite3.Connection,
    deps: Strategy150maDeps,
    start_date: str,
    end_date: str,
    capital: float,
) -> dict[str, Any]:
    symbols = deps.list_universe_symbols(conn)
    reports: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for item in symbols:
        try:
            report = run_backtest_150ma(
                conn,
                deps,
                symbol=item["symbol"],
                start_date=start_date,
                end_date=end_date,
                capital=capital,
                report_path=None,
                report_html=None,
            )
            if report["kind"] == "backtest_report":
                reports.append(report)
            else:
                skipped.append(report)
        except Exception as exc:
            failed.append({"symbol": item["symbol"], "message": str(exc)})

    sorted_reports = sorted(reports, key=lambda row: row["total_return"], reverse=True)
    return {
        "kind": "batch_backtest_report",
        "start_date": start_date,
        "end_date": end_date,
        "capital": capital,
        "total_symbols": len(symbols),
        "success_symbols": len(reports),
        "skipped_symbols": len(skipped),
        "failed_symbols": len(failed),
        "top_results": sorted_reports[:20],
        "skipped": skipped,
        "failures": failed,
    }
