#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from strategies.strategy_150ma import (
    Strategy150maDeps,
    batch_backtest_150ma as strategy_batch_backtest_150ma,
    batch_signal_150ma as strategy_batch_signal_150ma,
    build_strategy_data_check as strategy_build_strategy_data_check,
    compute_signal_150ma as strategy_compute_signal_150ma,
    create_trade_plan as strategy_create_trade_plan,
    run_backtest_150ma as strategy_run_backtest_150ma,
)
from technical_analysis import build_technical_payload

STRATEGY_ID = "strategy-150MA"
STRATEGY_VERSION = "v1"
UNIVERSE_ID = "cn-sector-etf-core"
BACKTEST_RECENCY_DAYS = 30
DEFAULT_FETCH_RETRIES = 3
DEFAULT_FETCH_RETRY_DELAY_SECONDS = 1.0
DEFAULT_DISCOVERY_KEYWORDS = [
    "芯片",
    "卫星",
    "电力",
    "煤炭",
    "通信",
    "证券",
    "银行",
    "军工",
    "医药",
    "新能源",
    "有色",
]
INDUSTRY_KEYWORD_ALIASES = {
    "芯片": ["芯片", "半导体"],
    "卫星": ["卫星", "航天", "航空航天"],
    "电力": ["电力", "绿色电力"],
    "煤炭": ["煤炭"],
    "通信": ["通信"],
    "证券": ["证券", "券商"],
    "银行": ["银行"],
    "军工": ["军工"],
    "医药": ["医药", "医疗", "创新药"],
    "新能源": ["新能源", "光伏", "储能", "电池"],
    "有色": ["有色"],
}
EXCLUDED_ETF_KEYWORDS = [
    "沪深300",
    "300ETF",
    "500ETF",
    "800",
    "A50",
    "A100",
    "A500",
    "中证500",
    "上证50",
    "创业板",
    "科创",
    "红利",
    "黄金",
    "纳指",
    "纳斯达克",
    "标普",
    "美股",
    "港股",
    "债",
    "货币",
    "REIT",
    "REITs",
    "跨境",
    "国债",
    "恒生",
    "消费",
    "中概",
    "互联",
    "货币",
    "现金",
    "快线",
    "标普",
    "MSCI",
    "ESG",
    "AH",
    "双创",
    "国企",
    "港股",
]
NON_INDUSTRY_ETF_KEYWORDS = [
    "财富宝",
    "快钱",
    "日利",
    "日盈",
    "天天金",
    "天天利",
    "添利",
    "上海金",
    "黄金",
    "商品",
    "指数",
    "日经",
    "道琼斯",
    "东南亚",
    "高股息",
    "价值",
]

SCHEMA_SQL = """
create table if not exists market_bars_1d (
  symbol text not null,
  name text not null,
  trade_date text not null,
  open real not null,
  close real not null,
  high real not null,
  low real not null,
  volume real not null,
  adjust_type text not null default 'qfq',
  source text not null default 'akshare',
  updated_at text not null,
  primary key (symbol, trade_date, adjust_type)
);
create table if not exists market_universes (
  universe_id text primary key,
  name text not null,
  status text not null default 'active',
  created_at text not null
);
create table if not exists market_universe_members (
  universe_id text not null,
  symbol text not null,
  name text not null,
  asset_type text not null,
  sector_name text not null,
  is_sector_etf integer not null default 1,
  enabled integer not null default 1,
  effective_from text,
  effective_to text,
  primary key (universe_id, symbol)
);
create table if not exists strategy_definitions (
  strategy_id text primary key,
  name text not null,
  type text not null,
  market_scope text not null,
  description text,
  created_at text not null
);
create table if not exists strategy_versions (
  strategy_id text not null,
  version text not null,
  parameters_json text not null,
  rules_json text not null,
  enabled integer not null default 1,
  created_at text not null,
  primary key (strategy_id, version)
);
create table if not exists strategy_execution_policies (
  strategy_id text not null,
  version text not null,
  allowed_universe_id text not null,
  allowed_asset_type text not null,
  allowed_market_scope text not null,
  require_latest_sync integer not null default 1,
  require_recent_backtest_for_live integer not null default 1,
  max_backtest_staleness_days integer not null default 30,
  created_at text not null,
  primary key (strategy_id, version)
);
create table if not exists strategy_backtest_runs (
  run_id text primary key,
  strategy_id text not null,
  version text not null,
  symbol text not null,
  start_date text not null,
  end_date text not null,
  total_return real,
  annual_return real,
  max_drawdown real,
  win_rate real,
  trade_count integer,
  report_path text,
  status text not null,
  created_at text not null
);
create table if not exists trading_trade_plans (
  plan_id text primary key,
  strategy_id text not null,
  version text not null,
  symbol text not null,
  trade_mode text not null,
  signal_date text not null,
  action text not null,
  target_position real not null,
  rationale text not null,
  status text not null,
  created_at text not null
);
create table if not exists ops_sync_runs (
  sync_id text primary key,
  sync_type text not null,
  trade_date text,
  status text not null,
  total_symbols integer not null default 0,
  success_symbols integer not null default 0,
  failed_symbols integer not null default 0,
  started_at text not null,
  finished_at text
);
"""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def die(message: str, code: int = 1) -> None:
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(code)


def load_pandas():
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required. Install requirements.txt first.") from exc
    return pd


def load_akshare():
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError("akshare is required. Install requirements.txt first.") from exc
    return ak


def parse_keyword_list(raw_keywords: str | None) -> list[str]:
    if not raw_keywords:
        return []
    parts = [item.strip() for item in raw_keywords.split(",")]
    return [item for item in parts if item]


def expand_keyword_aliases(keywords: list[str]) -> dict[str, list[str]]:
    expanded: dict[str, list[str]] = {}
    for keyword in keywords:
        expanded[keyword] = INDUSTRY_KEYWORD_ALIASES.get(keyword, [keyword])
    return expanded


def is_on_exchange_etf_by_code(code: str) -> bool:
    return code.startswith(("15", "51", "56", "58"))


def is_industry_etf_name(name: str) -> bool:
    return "ETF" in name


def matches_industry_keyword(name: str, aliases_by_keyword: dict[str, list[str]]) -> str | None:
    for keyword, aliases in aliases_by_keyword.items():
        if any(alias in name for alias in aliases):
            return keyword
    return None


def is_generic_etf_name(name: str) -> bool:
    return name.endswith("ETF")


def derive_sector_name(name: str) -> str:
    return name.removesuffix("ETF").strip()


def is_candidate_sector_name(sector_name: str) -> bool:
    if not sector_name:
        return False
    if any(ch.isdigit() for ch in sector_name):
        return False
    if any("A" <= ch <= "Z" or "a" <= ch <= "z" for ch in sector_name):
        return False
    if len(sector_name) <= 1:
        return False
    return True


def contains_excluded_keyword(name: str) -> str | None:
    for keyword in EXCLUDED_ETF_KEYWORDS:
        if keyword in name:
            return keyword
    return None


def contains_non_industry_keyword(name: str) -> str | None:
    for keyword in NON_INDUSTRY_ETF_KEYWORDS:
        if keyword in name:
            return keyword
    return None


def get_universe_members(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        select symbol, name, sector_name
        from market_universe_members
        where universe_id = ? and enabled = 1
        order by symbol
        """,
        (UNIVERSE_ID,),
    ).fetchall()


def classify_industry_etf_candidate(symbol: str, name: str, sector_name: str) -> tuple[bool, str | None]:
    excluded_keyword = contains_excluded_keyword(name)
    if excluded_keyword:
        return False, f"matched excluded keyword: {excluded_keyword}"
    non_industry_keyword = contains_non_industry_keyword(name)
    if non_industry_keyword:
        return False, f"matched non-industry keyword: {non_industry_keyword}"
    if not is_on_exchange_etf_by_code(symbol):
        return False, "not an on-exchange ETF code"
    if not is_industry_etf_name(name):
        return False, "name does not contain ETF"
    if not is_generic_etf_name(name):
        return False, "name is not a generic ETF name"
    if "联接" in name or "LOF" in name:
        return False, "linked fund or LOF is not allowed"
    if not is_candidate_sector_name(sector_name):
        return False, "sector name is not a valid industry candidate"
    return True, None


def discover_industry_etfs(keywords: list[str]) -> list[dict[str, str]]:
    ak = load_akshare()
    df = ak.fund_etf_spot_em()
    aliases_by_keyword = expand_keyword_aliases(keywords) if keywords else {}
    records: list[dict[str, str]] = []
    seen_codes: set[str] = set()

    for _, row in df.iterrows():
        code = str(row["代码"]).strip()
        name = str(row["名称"]).strip()
        if not code or not name:
            continue
        if code in seen_codes:
            continue
        sector_name = derive_sector_name(name)
        is_valid, _ = classify_industry_etf_candidate(code, name, sector_name)
        if not is_valid:
            continue
        if aliases_by_keyword:
            matched_keyword = matches_industry_keyword(name, aliases_by_keyword)
            if not matched_keyword:
                continue
            sector_name = matched_keyword

        seen_codes.add(code)
        records.append(
            {
                "symbol": code,
                "name": name,
                "sector_name": sector_name,
                "fund_type": "ETF-场内",
            }
        )

    records.sort(key=lambda item: (item["sector_name"], item["symbol"]))
    return records


def audit_universe_members(conn: sqlite3.Connection) -> dict[str, Any]:
    flagged: list[dict[str, Any]] = []
    clean: list[dict[str, Any]] = []
    for row in get_universe_members(conn):
        symbol = str(row["symbol"])
        name = str(row["name"])
        sector_name = str(row["sector_name"])
        is_valid, reason = classify_industry_etf_candidate(symbol, name, sector_name)
        payload = {
            "symbol": symbol,
            "name": name,
            "sector_name": sector_name,
        }
        if is_valid:
            clean.append(payload)
        else:
            flagged.append({**payload, "reason": reason})
    return {
        "kind": "universe_audit_report",
        "universe_id": UNIVERSE_ID,
        "total_symbols": len(flagged) + len(clean),
        "flagged_count": len(flagged),
        "clean_count": len(clean),
        "flagged": flagged,
    }


def prune_non_industry_universe_members(conn: sqlite3.Connection, csv_path: str | None) -> dict[str, Any]:
    audit_report = audit_universe_members(conn)
    removed_symbols = [row["symbol"] for row in audit_report["flagged"]]
    if removed_symbols:
        placeholders = ", ".join("?" for _ in removed_symbols)
        conn.execute(
            f"""
            delete from market_universe_members
            where universe_id = ? and symbol in ({placeholders})
            """,
            [UNIVERSE_ID, *removed_symbols],
        )
        conn.commit()

    updated_csv_path: str | None = None
    if csv_path:
        path = Path(csv_path).expanduser()
        if path.exists():
            removed_set = set(removed_symbols)
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = [row for row in reader if str(row.get("symbol") or "").strip() not in removed_set]
            fieldnames = reader.fieldnames or ["symbol", "name", "sector_name", "fund_type"]
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            updated_csv_path = str(path)

    return {
        "kind": "universe_prune_report",
        "universe_id": UNIVERSE_ID,
        "removed_count": len(removed_symbols),
        "removed_symbols": removed_symbols,
        "updated_csv_path": updated_csv_path,
        "audit_report": audit_report,
    }


def write_candidate_csv(output_path: str, rows: list[dict[str, str]]) -> str:
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "name", "sector_name", "fund_type"])
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


@dataclass
class Bar:
    symbol: str
    name: str
    trade_date: str
    open: float
    close: float
    high: float
    low: float
    volume: float
    adjust_type: str = "qfq"
    source: str = "akshare"
    updated_at: str = utc_now()


@dataclass
class FetchFailure(Exception):
    code: str
    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


def connect_db(db_path: str) -> sqlite3.Connection:
    resolved = Path(db_path).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(resolved)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    created_at = utc_now()
    conn.execute(
        """
        insert or ignore into market_universes (universe_id, name, status, created_at)
        values (?, ?, ?, ?)
        """,
        (UNIVERSE_ID, "A股行业场内ETF最小测试池", "active", created_at),
    )
    conn.execute(
        """
        insert or ignore into strategy_definitions
        (strategy_id, name, type, market_scope, description, created_at)
        values (?, ?, ?, ?, ?, ?)
        """,
        (
            STRATEGY_ID,
            "150日均线突破策略",
            "trend_following",
            "行业场内ETF",
            "收盘价上穿150MA买入100%，收盘价下穿150MA卖出全部仓位。",
            created_at,
        ),
    )
    conn.execute(
        """
        insert or ignore into strategy_execution_policies
        (strategy_id, version, allowed_universe_id, allowed_asset_type, allowed_market_scope, require_latest_sync, require_recent_backtest_for_live, max_backtest_staleness_days, created_at)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            STRATEGY_ID,
            STRATEGY_VERSION,
            UNIVERSE_ID,
            "ETF",
            "行业场内ETF",
            1,
            1,
            BACKTEST_RECENCY_DAYS,
            created_at,
        ),
    )
    conn.execute(
        """
        insert into strategy_versions
        (strategy_id, version, parameters_json, rules_json, enabled, created_at)
        values (?, ?, ?, ?, ?, ?)
        on conflict(strategy_id, version) do update set
          parameters_json = excluded.parameters_json,
          rules_json = excluded.rules_json,
          enabled = excluded.enabled
        """,
        (
            STRATEGY_ID,
            STRATEGY_VERSION,
            json.dumps(
                {
                    "ma_window": 150,
                    "indicator_ref": {
                        "ma_field": "ma_150",
                    },
                    "target_position": 1.0,
                    "signal_basis": "daily_close",
                    "execution_timing": "next_trading_day",
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "buy": "close crosses above ma150",
                    "sell": "close crosses below ma150",
                },
                ensure_ascii=False,
            ),
            1,
            created_at,
        ),
    )
    conn.commit()


def seed_universe(conn: sqlite3.Connection, csv_path: str) -> dict[str, Any]:
    with open(csv_path, "r", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    loaded = 0
    for row in rows:
        symbol = (row.get("symbol") or "").strip()
        name = (row.get("name") or "").strip()
        sector_name = (row.get("sector_name") or "").strip()
        if not symbol or not name or not sector_name:
            continue
        conn.execute(
            """
            insert into market_universe_members
            (universe_id, symbol, name, asset_type, sector_name, is_sector_etf, enabled)
            values (?, ?, ?, ?, ?, 1, 1)
            on conflict(universe_id, symbol) do update set
              name=excluded.name,
              asset_type=excluded.asset_type,
              sector_name=excluded.sector_name,
              is_sector_etf=excluded.is_sector_etf,
              enabled=excluded.enabled
            """,
            (UNIVERSE_ID, symbol, name, "ETF", sector_name),
        )
        loaded += 1
    conn.commit()
    return {"kind": "universe_seed_report", "universe_id": UNIVERSE_ID, "loaded": loaded}


def seed_universe_rows(conn: sqlite3.Connection, rows: list[dict[str, str]]) -> dict[str, Any]:
    loaded = 0
    for row in rows:
        symbol = (row.get("symbol") or "").strip()
        name = (row.get("name") or "").strip()
        sector_name = (row.get("sector_name") or "").strip()
        if not symbol or not name or not sector_name:
            continue
        conn.execute(
            """
            insert into market_universe_members
            (universe_id, symbol, name, asset_type, sector_name, is_sector_etf, enabled)
            values (?, ?, ?, ?, ?, 1, 1)
            on conflict(universe_id, symbol) do update set
              name=excluded.name,
              asset_type=excluded.asset_type,
              sector_name=excluded.sector_name,
              is_sector_etf=excluded.is_sector_etf,
              enabled=excluded.enabled
            """,
            (UNIVERSE_ID, symbol, name, "ETF", sector_name),
        )
        loaded += 1
    conn.commit()
    return {"kind": "universe_seed_report", "universe_id": UNIVERSE_ID, "loaded": loaded}


def count_universe_members(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        select count(*) as count
        from market_universe_members
        where universe_id = ? and enabled = 1
        """,
        (UNIVERSE_ID,),
    ).fetchone()
    return int(row["count"] or 0) if row else 0


def list_universe_symbols(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        select symbol, name, sector_name
        from market_universe_members
        where universe_id = ? and enabled = 1 and is_sector_etf = 1 and asset_type = 'ETF'
        order by symbol
        """,
        (UNIVERSE_ID,),
    ).fetchall()


def bootstrap_db(conn: sqlite3.Connection, db_path: str, csv_path: str | None) -> dict[str, Any]:
    init_db(conn)
    seed_report: dict[str, Any] | None = None
    csv_exists = False
    resolved_csv: str | None = None
    if csv_path:
        csv_file = Path(csv_path).expanduser()
        resolved_csv = str(csv_file)
        csv_exists = csv_file.exists()
    universe_count = count_universe_members(conn)
    if universe_count == 0 and csv_exists and resolved_csv:
        seed_report = seed_universe(conn, resolved_csv)
        universe_count = count_universe_members(conn)

    latest_trade_date: str | None = None
    try:
        latest_trade_date = get_latest_market_trade_date(conn)
    except RuntimeError:
        latest_trade_date = None

    return {
        "kind": "bootstrap_db",
        "db": db_path,
        "csv_path": resolved_csv,
        "csv_exists": csv_exists,
        "seeded": seed_report is not None,
        "universe_symbols": universe_count,
        "latest_trade_date": latest_trade_date,
        "seed_report": seed_report,
    }


def normalize_bars(raw_df: Any, symbol: str, name: str) -> list[Bar]:
    pd = load_pandas()
    if getattr(raw_df, "empty", False):
        raise FetchFailure("empty_data", f"No daily bars returned by AkShare for {symbol} in the requested date range.", retryable=False)
    rename_map = {
        "日期": "trade_date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
    }
    df = raw_df.rename(columns=rename_map).copy()
    required = ["trade_date", "open", "close", "high", "low", "volume"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise FetchFailure("schema_error", f"Missing expected AkShare columns: {missing}", retryable=False)

    df = df[required].dropna()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    for column in ["open", "close", "high", "low", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna()

    bars: list[Bar] = []
    for _, row in df.iterrows():
        bars.append(
            Bar(
                symbol=symbol,
                name=name,
                trade_date=str(row["trade_date"]),
                open=float(row["open"]),
                close=float(row["close"]),
                high=float(row["high"]),
                low=float(row["low"]),
                volume=float(row["volume"]),
            )
        )
    return bars


def fetch_etf_history(symbol: str, name: str, start_date: str, end_date: str) -> list[Bar]:
    ak = load_akshare()
    try:
        raw_df = ak.fund_etf_hist_em(
            symbol=symbol,
            period="daily",
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust="qfq",
        )
    except Exception as exc:
        raise FetchFailure("transient_error", f"AkShare request failed for {symbol}: {exc}", retryable=True) from exc
    return normalize_bars(raw_df, symbol=symbol, name=name)


def fetch_etf_history_with_retry(
    symbol: str,
    name: str,
    start_date: str,
    end_date: str,
    retries: int = DEFAULT_FETCH_RETRIES,
    retry_delay_seconds: float = DEFAULT_FETCH_RETRY_DELAY_SECONDS,
) -> tuple[list[Bar] | None, dict[str, Any]]:
    last_error: FetchFailure | None = None
    attempts = max(retries, 1)
    for attempt in range(1, attempts + 1):
        try:
            bars = fetch_etf_history(symbol=symbol, name=name, start_date=start_date, end_date=end_date)
            return bars, {"attempts": attempt, "retried": attempt > 1}
        except FetchFailure as exc:
            last_error = exc
            if not exc.retryable or attempt >= attempts:
                break
            time.sleep(retry_delay_seconds * attempt)
        except Exception as exc:
            last_error = FetchFailure("unexpected_error", str(exc), retryable=False)
            break

    assert last_error is not None
    return None, {
        "attempts": attempts,
        "retried": attempts > 1,
        "error_code": last_error.code,
        "error_message": last_error.message,
    }


def build_trading_dates(start_date: str, days: int) -> list[date]:
    current = date.fromisoformat(start_date)
    trading_dates: list[date] = []
    while len(trading_dates) < days:
        if current.weekday() < 5:
            trading_dates.append(current)
        current += timedelta(days=1)
    return trading_dates


def generate_demo_bars(symbol: str, name: str, start_date: str, days: int, trend: str) -> list[Bar]:
    if days < 160:
        raise RuntimeError("seed-demo-bars requires at least 160 trading days to support 150MA testing.")

    trading_dates = build_trading_dates(start_date, days)
    bars: list[Bar] = []
    for idx, trading_day in enumerate(trading_dates):
        if trend == "bullish":
            pivot = days - 18
            if idx < pivot:
                base_close = 125.0 - idx * 0.14
            else:
                base_close = 125.0 - pivot * 0.14 + (idx - pivot + 1) * 1.85
        elif trend == "bearish":
            pivot = days - 18
            if idx < pivot:
                base_close = 92.0 + idx * 0.14
            else:
                base_close = 92.0 + pivot * 0.14 - (idx - pivot + 1) * 1.75
        elif trend == "signal-buy":
            if idx < days - 1:
                base_close = 123.0 - idx * 0.16
            else:
                base_close = 132.0
        elif trend == "signal-sell":
            if idx < days - 1:
                base_close = 96.0 + idx * 0.16
            else:
                base_close = 86.0
        else:
            wave = math.sin(idx / 9.0) * 2.4
            drift = idx * 0.015
            base_close = 110.0 + wave + drift

        open_price = base_close * 0.997
        high_price = base_close * 1.012
        low_price = base_close * 0.988
        volume = 1_000_000 + idx * 1500
        bars.append(
            Bar(
                symbol=symbol,
                name=name,
                trade_date=trading_day.isoformat(),
                open=round(open_price, 4),
                close=round(base_close, 4),
                high=round(high_price, 4),
                low=round(low_price, 4),
                volume=float(round(volume, 2)),
            )
        )
    return bars


def seed_demo_bars(conn: sqlite3.Connection, start_date: str, days: int, trend: str, record_sync: bool) -> dict[str, Any]:
    symbols = list_universe_symbols(conn)
    if not symbols:
        raise RuntimeError("Universe is empty. Run seed-universe before seed-demo-bars.")

    sync_id: str | None = None
    last_trade_date = build_trading_dates(start_date, days)[-1].isoformat()
    if record_sync:
        sync_id = record_sync_start(conn, "sync_daily", last_trade_date)

    details: list[dict[str, Any]] = []
    total_rows = 0
    for item in symbols:
        bars = generate_demo_bars(item["symbol"], item["name"], start_date=start_date, days=days, trend=trend)
        inserted = upsert_bars(conn, bars)
        total_rows += inserted
        details.append(
            {
                "symbol": item["symbol"],
                "name": item["name"],
                "rows": inserted,
                "first_trade_date": bars[0].trade_date,
                "last_trade_date": bars[-1].trade_date,
                "trend": trend,
            }
        )

    if sync_id is not None:
        record_sync_finish(conn, sync_id, "completed", len(symbols), len(symbols), 0)

    return {
        "kind": "demo_seed_report",
        "universe_id": UNIVERSE_ID,
        "symbols": len(symbols),
        "rows": total_rows,
        "days": days,
        "trend": trend,
        "sync_recorded": record_sync,
        "trade_date": last_trade_date,
        "details": details,
    }


def upsert_bars(conn: sqlite3.Connection, bars: list[Bar]) -> int:
    for bar in bars:
        conn.execute(
            """
            insert into market_bars_1d
            (symbol, name, trade_date, open, close, high, low, volume, adjust_type, source, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(symbol, trade_date, adjust_type) do update set
              name=excluded.name,
              open=excluded.open,
              close=excluded.close,
              high=excluded.high,
              low=excluded.low,
              volume=excluded.volume,
              source=excluded.source,
              updated_at=excluded.updated_at
            """,
            (
                bar.symbol,
                bar.name,
                bar.trade_date,
                bar.open,
                bar.close,
                bar.high,
                bar.low,
                bar.volume,
                bar.adjust_type,
                bar.source,
                bar.updated_at,
            ),
        )
    conn.commit()
    return len(bars)


def record_sync_start(conn: sqlite3.Connection, sync_type: str, trade_date: str | None) -> str:
    sync_id = str(uuid.uuid4())
    conn.execute(
        """
        insert into ops_sync_runs
        (sync_id, sync_type, trade_date, status, started_at)
        values (?, ?, ?, ?, ?)
        """,
        (sync_id, sync_type, trade_date, "running", utc_now()),
    )
    conn.commit()
    return sync_id


def record_sync_finish(conn: sqlite3.Connection, sync_id: str, status: str, total_symbols: int, success_symbols: int, failed_symbols: int) -> None:
    conn.execute(
        """
        update ops_sync_runs
        set status = ?, total_symbols = ?, success_symbols = ?, failed_symbols = ?, finished_at = ?
        where sync_id = ?
        """,
        (status, total_symbols, success_symbols, failed_symbols, utc_now(), sync_id),
    )
    conn.commit()


def bootstrap_history(conn: sqlite3.Connection, start_date: str, end_date: str) -> dict[str, Any]:
    symbols = list_universe_symbols(conn)
    sync_id = record_sync_start(conn, "bootstrap_history", end_date)
    success = 0
    failed = 0
    retried_symbols = 0
    retried_success_symbols = 0
    empty_data_symbols = 0
    details: list[dict[str, Any]] = []

    for item in symbols:
        bars, meta = fetch_etf_history_with_retry(item["symbol"], item["name"], start_date=start_date, end_date=end_date)
        if meta.get("retried"):
            retried_symbols += 1
        if bars is not None:
            inserted = upsert_bars(conn, bars)
            success += 1
            if meta.get("retried"):
                retried_success_symbols += 1
            details.append(
                {
                    "symbol": item["symbol"],
                    "status": "ok",
                    "rows": inserted,
                    "attempts": meta["attempts"],
                    "retried": meta["retried"],
                }
            )
            continue

        failed += 1
        if meta.get("error_code") == "empty_data":
            empty_data_symbols += 1
        details.append(
            {
                "symbol": item["symbol"],
                "status": "error",
                "message": meta["error_message"],
                "error_code": meta["error_code"],
                "attempts": meta["attempts"],
                "retried": meta["retried"],
            }
        )

    status = "completed" if failed == 0 else "partial"
    record_sync_finish(conn, sync_id, status, len(symbols), success, failed)
    return {
        "kind": "sync_report",
        "sync_id": sync_id,
        "sync_type": "bootstrap_history",
        "status": status,
        "total_symbols": len(symbols),
        "success_symbols": success,
        "failed_symbols": failed,
        "retried_symbols": retried_symbols,
        "retried_success_symbols": retried_success_symbols,
        "empty_data_symbols": empty_data_symbols,
        "details": details,
    }


def sync_daily(conn: sqlite3.Connection, trade_date: str | None) -> dict[str, Any]:
    target = trade_date or date.today().isoformat()
    sync_id = record_sync_start(conn, "sync_daily", target)
    symbols = list_universe_symbols(conn)
    success = 0
    failed = 0
    retried_symbols = 0
    retried_success_symbols = 0
    empty_data_symbols = 0
    backfilled_symbols = 0
    total_gap_days = 0
    details: list[dict[str, Any]] = []

    for item in symbols:
        latest_row = conn.execute(
            """
            select max(trade_date) as trade_date
            from market_bars_1d
            where symbol = ?
            """,
            (item["symbol"],),
        ).fetchone()
        latest_trade_date = str(latest_row["trade_date"]) if latest_row and latest_row["trade_date"] else None
        gap_days = 0
        if latest_trade_date is not None:
            gap_days = max((date.fromisoformat(target) - date.fromisoformat(latest_trade_date)).days, 0)
        fetch_start = target if latest_trade_date is None else (
            date.fromisoformat(latest_trade_date) + timedelta(days=1)
        ).isoformat()

        if fetch_start > target:
            success += 1
            details.append(
                {
                    "symbol": item["symbol"],
                    "status": "up_to_date",
                    "rows": 0,
                    "fetch_start": fetch_start,
                    "fetch_end": target,
                    "latest_trade_date_before_sync": latest_trade_date,
                    "gap_days": gap_days,
                    "backfilled": False,
                    "attempts": 0,
                    "retried": False,
                }
            )
            continue

        bars, meta = fetch_etf_history_with_retry(item["symbol"], item["name"], start_date=fetch_start, end_date=target)
        if meta.get("retried"):
            retried_symbols += 1
        if bars is not None:
            inserted = upsert_bars(conn, bars)
            success += 1
            if latest_trade_date is None or fetch_start < target:
                backfilled_symbols += 1
            total_gap_days += gap_days
            if meta.get("retried"):
                retried_success_symbols += 1
            details.append(
                {
                    "symbol": item["symbol"],
                    "status": "ok",
                    "rows": inserted,
                    "fetch_start": fetch_start,
                    "fetch_end": target,
                    "latest_trade_date_before_sync": latest_trade_date,
                    "gap_days": gap_days,
                    "backfilled": latest_trade_date is None or fetch_start < target,
                    "first_trade_date": bars[0].trade_date if bars else None,
                    "last_trade_date": bars[-1].trade_date if bars else None,
                    "attempts": meta["attempts"],
                    "retried": meta["retried"],
                }
            )
            continue

        failed += 1
        if meta.get("error_code") == "empty_data":
            empty_data_symbols += 1
        details.append(
            {
                "symbol": item["symbol"],
                "status": "error",
                "fetch_start": fetch_start,
                "fetch_end": target,
                "latest_trade_date_before_sync": latest_trade_date,
                "gap_days": gap_days,
                "backfilled": latest_trade_date is None or fetch_start < target,
                "message": meta["error_message"],
                "error_code": meta["error_code"],
                "attempts": meta["attempts"],
                "retried": meta["retried"],
            }
        )

    status = "completed" if failed == 0 else "partial"
    record_sync_finish(conn, sync_id, status, len(symbols), success, failed)
    coverage_summary = get_trade_date_coverage_summary(conn, target)
    top_movers: dict[str, Any] | None = None
    strategy_daily_report: dict[str, Any] | None = None
    if coverage_summary["covered_symbols"] > 0:
        top_movers = get_top_etf_movers_report(conn, trade_date=target, top_n=10)
        strategy_daily_report = build_strategy_daily_report(conn, trade_date=target)
    return {
        "kind": "sync_report",
        "sync_id": sync_id,
        "sync_type": "sync_daily",
        "trade_date": target,
        "status": status,
        "total_symbols": len(symbols),
        "success_symbols": success,
        "failed_symbols": failed,
        "retried_symbols": retried_symbols,
        "retried_success_symbols": retried_success_symbols,
        "empty_data_symbols": empty_data_symbols,
        "backfilled_symbols": backfilled_symbols,
        "total_gap_days": total_gap_days,
        "coverage_summary": coverage_summary,
        "top_movers": top_movers,
        "strategy_daily_report": strategy_daily_report,
        "details": details,
    }


def load_symbol_bars(conn: sqlite3.Connection, symbol: str, start_date: str | None = None, end_date: str | None = None):
    pd = load_pandas()
    sql = """
        select symbol, name, trade_date, open, close, high, low, volume
        from market_bars_1d
        where symbol = ?
    """
    params: list[Any] = [symbol]
    if start_date:
        sql += " and trade_date >= ?"
        params.append(start_date)
    if end_date:
        sql += " and trade_date <= ?"
        params.append(end_date)
    sql += " order by trade_date"
    df = pd.read_sql_query(sql, conn, params=params)
    if df.empty:
        raise RuntimeError(f"No bars found for {symbol}")
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df


def ensure_symbol_allowed(conn: sqlite3.Connection, symbol: str) -> sqlite3.Row:
    row = conn.execute(
        """
        select symbol, name, sector_name
        from market_universe_members
        where universe_id = ? and symbol = ? and enabled = 1 and is_sector_etf = 1 and asset_type = 'ETF'
        """,
        (UNIVERSE_ID, symbol),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Symbol {symbol} is not in the allowed industry ETF universe.")
    return row


def get_latest_trade_date(conn: sqlite3.Connection, symbol: str) -> str:
    row = conn.execute(
        """
        select max(trade_date) as trade_date
        from market_bars_1d
        where symbol = ?
        """,
        (symbol,),
    ).fetchone()
    trade_date = row["trade_date"] if row else None
    if not trade_date:
        raise RuntimeError(f"No bars found for {symbol}")
    return str(trade_date)


def get_strategy_policy(conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute(
        """
        select strategy_id, version, allowed_universe_id, allowed_asset_type, allowed_market_scope, require_latest_sync, require_recent_backtest_for_live, max_backtest_staleness_days
        from strategy_execution_policies
        where strategy_id = ? and version = ?
        """,
        (STRATEGY_ID, STRATEGY_VERSION),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Missing execution policy for {STRATEGY_ID}:{STRATEGY_VERSION}")
    return row


def get_last_sync_status(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        """
        select sync_id, sync_type, trade_date, status, total_symbols, success_symbols, failed_symbols, started_at, finished_at
        from ops_sync_runs
        where sync_type = 'sync_daily'
        order by started_at desc
        limit 1
        """
    ).fetchone()


def require_latest_sync(conn: sqlite3.Connection, symbol: str) -> dict[str, Any]:
    latest_trade_date = get_latest_trade_date(conn, symbol)
    last_sync = get_last_sync_status(conn)
    if last_sync is None:
        raise RuntimeError("Daily sync has not been run yet. Run sync-daily before creating a trade plan.")
    if str(last_sync["status"]) != "completed":
        raise RuntimeError("Latest daily sync did not complete successfully. Resolve sync failures before creating a trade plan.")
    if str(last_sync["trade_date"]) != latest_trade_date:
        raise RuntimeError(
            f"Latest daily sync trade_date {last_sync['trade_date']} does not match latest bar date {latest_trade_date} for {symbol}."
        )
    return {
        "sync_id": str(last_sync["sync_id"]),
        "trade_date": latest_trade_date,
        "status": str(last_sync["status"]),
        "finished_at": str(last_sync["finished_at"] or ""),
    }


def load_latest_backtest(conn: sqlite3.Connection, symbol: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        select run_id, strategy_id, version, symbol, start_date, end_date, total_return, annual_return, max_drawdown, win_rate, trade_count, report_path, status, created_at
        from strategy_backtest_runs
        where strategy_id = ? and version = ? and symbol = ? and status = 'completed'
        order by end_date desc, created_at desc
        limit 1
        """,
        (STRATEGY_ID, STRATEGY_VERSION, symbol),
    ).fetchone()


def require_recent_backtest(conn: sqlite3.Connection, symbol: str, signal_trade_date: str) -> dict[str, Any]:
    latest_backtest = load_latest_backtest(conn, symbol)
    if latest_backtest is None:
        raise RuntimeError(f"No completed backtest found for {symbol}. Run backtest-150ma before live trading.")

    backtest_end = date.fromisoformat(str(latest_backtest["end_date"]))
    signal_date = date.fromisoformat(signal_trade_date)
    staleness_days = (signal_date - backtest_end).days
    if staleness_days < 0:
        staleness_days = 0

    policy = get_strategy_policy(conn)
    max_staleness_days = int(policy["max_backtest_staleness_days"])
    if backtest_end < signal_date and staleness_days > max_staleness_days:
        raise RuntimeError(
            f"Latest backtest for {symbol} ended on {backtest_end.isoformat()}, which is older than {max_staleness_days} days relative to signal date {signal_trade_date}."
        )

    return {
        "run_id": str(latest_backtest["run_id"]),
        "end_date": str(latest_backtest["end_date"]),
        "trade_count": int(latest_backtest["trade_count"] or 0),
        "staleness_days": staleness_days,
    }


def get_sync_status_report(conn: sqlite3.Connection) -> dict[str, Any]:
    row = get_last_sync_status(conn)
    if row is None:
        row = conn.execute(
            """
            select sync_id, sync_type, trade_date, status, total_symbols, success_symbols, failed_symbols, started_at, finished_at
            from ops_sync_runs
            order by started_at desc
            limit 1
            """
        ).fetchone()
    if row is None:
        return {"kind": "sync_status", "status": "missing"}
    coverage_summary: dict[str, Any] | None = None
    trade_date = str(row["trade_date"] or "")
    if trade_date:
        coverage_summary = get_trade_date_coverage_summary(conn, trade_date)
    return {
        "kind": "sync_status",
        "sync_id": str(row["sync_id"]),
        "sync_type": str(row["sync_type"]),
        "trade_date": trade_date,
        "status": str(row["status"]),
        "total_symbols": int(row["total_symbols"]),
        "success_symbols": int(row["success_symbols"]),
        "failed_symbols": int(row["failed_symbols"]),
        "started_at": str(row["started_at"]),
        "finished_at": str(row["finished_at"] or ""),
        "coverage_summary": coverage_summary,
    }


def get_range_coverage_report(conn: sqlite3.Connection, start_date: str, end_date: str) -> dict[str, Any]:
    rows = conn.execute(
        """
        select m.symbol, m.name, m.sector_name, count(b.trade_date) as row_count, min(b.trade_date) as first_trade_date, max(b.trade_date) as last_trade_date
        from market_universe_members m
        left join market_bars_1d b
          on b.symbol = m.symbol
         and b.trade_date >= ?
         and b.trade_date <= ?
        where m.universe_id = ? and m.enabled = 1
        group by m.symbol, m.name, m.sector_name
        order by row_count asc, m.symbol asc
        """,
        (start_date, end_date, UNIVERSE_ID),
    ).fetchall()
    details = [
        {
            "symbol": str(row["symbol"]),
            "name": str(row["name"]),
            "sector_name": str(row["sector_name"]),
            "row_count": int(row["row_count"]),
            "first_trade_date": str(row["first_trade_date"] or ""),
            "last_trade_date": str(row["last_trade_date"] or ""),
        }
        for row in rows
    ]
    covered = sum(1 for row in details if row["row_count"] > 0)
    missing = sum(1 for row in details if row["row_count"] == 0)
    return {
        "kind": "coverage_report",
        "start_date": start_date,
        "end_date": end_date,
        "covered_symbols": covered,
        "missing_symbols": missing,
        "total_symbols": len(details),
        "details": details,
    }


def get_trade_date_coverage_summary(conn: sqlite3.Connection, trade_date: str) -> dict[str, Any]:
    coverage = get_range_coverage_report(conn, start_date=trade_date, end_date=trade_date)
    missing_symbols = [row["symbol"] for row in coverage["details"] if row["row_count"] == 0]
    return {
        "trade_date": trade_date,
        "covered_symbols": coverage["covered_symbols"],
        "missing_symbols": coverage["missing_symbols"],
        "total_symbols": coverage["total_symbols"],
        "is_complete": coverage["missing_symbols"] == 0,
        "missing_symbol_list": missing_symbols,
    }


def get_latest_market_trade_date(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        """
        select max(trade_date) as trade_date
        from market_bars_1d
        """
    ).fetchone()
    trade_date = row["trade_date"] if row else None
    if not trade_date:
        raise RuntimeError("No market bars found in database.")
    return str(trade_date)


def calculate_pct_change(current_close: float, previous_close: float) -> float:
    if previous_close == 0:
        return 0.0
    return (current_close - previous_close) / previous_close


def get_top_etf_movers(conn: sqlite3.Connection, trade_date: str, lookback_days: int, top_n: int = 10) -> list[dict[str, Any]]:
    if lookback_days < 1:
        raise RuntimeError("lookback_days must be >= 1")

    movers: list[dict[str, Any]] = []
    for item in list_universe_symbols(conn):
        rows = conn.execute(
            """
            select trade_date, close
            from market_bars_1d
            where symbol = ? and trade_date <= ?
            order by trade_date desc
            limit ?
            """,
            (item["symbol"], trade_date, lookback_days + 1),
        ).fetchall()
        if len(rows) < lookback_days + 1:
            continue

        latest_row = rows[0]
        previous_row = rows[lookback_days]
        latest_close = float(latest_row["close"])
        previous_close = float(previous_row["close"])
        pct_change = calculate_pct_change(latest_close, previous_close)
        movers.append(
            {
                "symbol": str(item["symbol"]),
                "name": str(item["name"]),
                "sector_name": str(item["sector_name"]),
                "trade_date": str(latest_row["trade_date"]),
                "lookback_days": lookback_days,
                "start_trade_date": str(previous_row["trade_date"]),
                "start_close": previous_close,
                "end_trade_date": str(latest_row["trade_date"]),
                "end_close": latest_close,
                "pct_change": pct_change,
            }
        )

    return sorted(movers, key=lambda row: row["pct_change"], reverse=True)[:top_n]


def get_top_etf_movers_report(conn: sqlite3.Connection, trade_date: str | None = None, top_n: int = 10) -> dict[str, Any]:
    target_trade_date = trade_date or get_latest_market_trade_date(conn)
    lookbacks = [1, 3, 5]
    periods: dict[str, Any] = {}
    for lookback_days in lookbacks:
        periods[f"top_{lookback_days}d"] = {
            "lookback_days": lookback_days,
            "top_n": top_n,
            "leaders": get_top_etf_movers(conn, target_trade_date, lookback_days=lookback_days, top_n=top_n),
        }
    return {
        "kind": "top_movers_report",
        "trade_date": target_trade_date,
        "periods": periods,
    }


def search_etfs(conn: sqlite3.Connection, query: str, limit: int = 10) -> dict[str, Any]:
    normalized = query.strip()
    if not normalized:
        raise RuntimeError("query is required")

    like_value = f"%{normalized}%"
    rows = conn.execute(
        """
        select
          m.symbol,
          m.name,
          m.sector_name,
          (
            select b.trade_date
            from market_bars_1d b
            where b.symbol = m.symbol
            order by b.trade_date desc
            limit 1
          ) as latest_trade_date,
          (
            select b.close
            from market_bars_1d b
            where b.symbol = m.symbol
            order by b.trade_date desc
            limit 1
          ) as latest_close
        from market_universe_members m
        where
          m.universe_id = ?
          and m.enabled = 1
          and m.is_sector_etf = 1
          and m.asset_type = 'ETF'
          and (
            m.symbol = ?
            or m.name = ?
            or m.sector_name = ?
            or m.symbol like ?
            or m.name like ?
            or m.sector_name like ?
          )
        order by
          case
            when m.symbol = ? then 0
            when m.name = ? then 1
            when m.sector_name = ? then 2
            when m.name like ? then 3
            when m.sector_name like ? then 4
            else 5
          end,
          m.symbol asc
        limit ?
        """,
        (
            UNIVERSE_ID,
            normalized,
            normalized,
            normalized,
            like_value,
            like_value,
            like_value,
            normalized,
            normalized,
            normalized,
            like_value,
            like_value,
            max(limit, 1),
        ),
    ).fetchall()

    matches = [
        {
            "symbol": str(row["symbol"]),
            "name": str(row["name"]),
            "sector_name": str(row["sector_name"]),
            "latest_trade_date": str(row["latest_trade_date"] or ""),
            "latest_close": float(row["latest_close"]) if row["latest_close"] is not None else None,
        }
        for row in rows
    ]
    exact_symbol_match = next((item for item in matches if item["symbol"] == normalized), None)
    exact_name_matches = [item for item in matches if item["name"] == normalized]
    exact_sector_matches = [item for item in matches if item["sector_name"] == normalized]
    resolved_symbol = exact_symbol_match["symbol"] if exact_symbol_match else None
    if not resolved_symbol and len(exact_name_matches) == 1:
        resolved_symbol = exact_name_matches[0]["symbol"]
    if not resolved_symbol and len(exact_sector_matches) == 1:
        resolved_symbol = exact_sector_matches[0]["symbol"]

    return {
        "kind": "etf_search",
        "query": normalized,
        "match_count": len(matches),
        "resolved_symbol": resolved_symbol,
        "matches": matches,
    }


def get_etf_latest_price(conn: sqlite3.Connection, symbol: str) -> dict[str, Any]:
    member = ensure_symbol_allowed(conn, symbol)
    row = conn.execute(
        """
        select trade_date, open, close, high, low, volume
        from market_bars_1d
        where symbol = ?
        order by trade_date desc
        limit 1
        """,
        (symbol,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"No market bars found for symbol {symbol}.")

    return {
        "kind": "etf_latest_price",
        "symbol": symbol,
        "name": str(member["name"]),
        "sector_name": str(member["sector_name"]),
        "trade_date": str(row["trade_date"]),
        "open": float(row["open"]),
        "close": float(row["close"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "volume": float(row["volume"]),
    }


def get_technical_indicators_report(
    conn: sqlite3.Connection,
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    recent_bars: int = 20,
) -> dict[str, Any]:
    member = ensure_symbol_allowed(conn, symbol)
    df = load_symbol_bars(conn, symbol, start_date=start_date, end_date=end_date)
    technical = build_technical_payload(df, recent_bars=recent_bars, include_series=False)
    return {
        "kind": "technical_indicators",
        "symbol": symbol,
        "name": str(member["name"]),
        "sector_name": str(member["sector_name"]),
        "trade_date": technical["trade_date"],
        "indicators": technical["indicators"],
    }


def get_technical_analysis_report(
    conn: sqlite3.Connection,
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    recent_bars: int = 20,
    include_series: bool = False,
) -> dict[str, Any]:
    member = ensure_symbol_allowed(conn, symbol)
    df = load_symbol_bars(conn, symbol, start_date=start_date, end_date=end_date)
    technical = build_technical_payload(df, recent_bars=recent_bars, include_series=include_series)
    technical["symbol"] = symbol
    technical["name"] = str(member["name"])
    technical["sector_name"] = str(member["sector_name"])
    return technical


def build_return_snapshot(df: Any, latest_index: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    latest_close = float(df.iloc[latest_index]["close"])
    latest_trade_date = df.iloc[latest_index]["trade_date"].strftime("%Y-%m-%d")
    for window in [1, 3, 5, 20]:
        if latest_index - window < 0:
            continue
        previous_row = df.iloc[latest_index - window]
        previous_close = float(previous_row["close"])
        result[f"{window}d"] = {
            "start_trade_date": previous_row["trade_date"].strftime("%Y-%m-%d"),
            "end_trade_date": latest_trade_date,
            "start_close": previous_close,
            "end_close": latest_close,
            "pct_change": calculate_pct_change(latest_close, previous_close),
        }
    return result


def get_etf_detail(
    conn: sqlite3.Connection,
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    recent_bars: int = 20,
) -> dict[str, Any]:
    member = ensure_symbol_allowed(conn, symbol)
    df = load_symbol_bars(conn, symbol, start_date=start_date, end_date=end_date)
    latest_index = len(df) - 1
    latest_row = df.iloc[latest_index]
    latest_trade_date = latest_row["trade_date"].strftime("%Y-%m-%d")
    return_snapshot = build_return_snapshot(df, latest_index)

    latest_bar = {
        "trade_date": latest_trade_date,
        "open": float(latest_row["open"]),
        "close": float(latest_row["close"]),
        "high": float(latest_row["high"]),
        "low": float(latest_row["low"]),
        "volume": float(latest_row["volume"]),
    }
    range_summary = {
        "start_date": df.iloc[0]["trade_date"].strftime("%Y-%m-%d"),
        "end_date": latest_trade_date,
        "bar_count": len(df),
        "window_start": start_date,
        "window_end": end_date,
    }
    recent_rows = df.tail(max(recent_bars, 1))
    recent_bars_payload = [
        {
            "trade_date": row["trade_date"].strftime("%Y-%m-%d"),
            "open": float(row["open"]),
            "close": float(row["close"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "volume": float(row["volume"]),
        }
        for _, row in recent_rows.iterrows()
    ]

    latest_signal: dict[str, Any] | None = None
    signal_result = compute_signal_150ma(conn, symbol)
    if signal_result["kind"] == "signal_report":
        latest_signal = signal_result
    technical_analysis = get_technical_analysis_report(
        conn,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        recent_bars=recent_bars,
        include_series=False,
    )

    return {
        "kind": "etf_detail",
        "symbol": symbol,
        "name": str(member["name"]),
        "sector_name": str(member["sector_name"]),
        "latest_bar": latest_bar,
        "returns": return_snapshot,
        "range_summary": range_summary,
        "recent_bars": recent_bars_payload,
        "technical_analysis": technical_analysis,
        "latest_signal": latest_signal,
    }


def prune_empty_universe_members(conn: sqlite3.Connection, start_date: str, end_date: str, csv_path: str | None) -> dict[str, Any]:
    coverage = get_range_coverage_report(conn, start_date=start_date, end_date=end_date)
    empty_symbols = [row["symbol"] for row in coverage["details"] if row["row_count"] == 0]
    if empty_symbols:
        placeholders = ", ".join("?" for _ in empty_symbols)
        conn.execute(
            f"""
            delete from market_universe_members
            where universe_id = ? and symbol in ({placeholders})
            """,
            [UNIVERSE_ID, *empty_symbols],
        )
        conn.commit()

    updated_csv_path: str | None = None
    if csv_path:
        path = Path(csv_path).expanduser()
        if path.exists():
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = [row for row in reader if str(row.get("symbol") or "").strip() not in set(empty_symbols)]
            fieldnames = reader.fieldnames or ["symbol", "name", "sector_name", "fund_type"]
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            updated_csv_path = str(path)

    return {
        "kind": "prune_report",
        "start_date": start_date,
        "end_date": end_date,
        "removed_symbols": empty_symbols,
        "removed_count": len(empty_symbols),
        "updated_csv_path": updated_csv_path,
    }


def get_strategy_report(conn: sqlite3.Connection) -> dict[str, Any]:
    definition = conn.execute(
        """
        select strategy_id, name, type, market_scope, description, created_at
        from strategy_definitions
        where strategy_id = ?
        """,
        (STRATEGY_ID,),
    ).fetchone()
    version = conn.execute(
        """
        select strategy_id, version, parameters_json, rules_json, enabled, created_at
        from strategy_versions
        where strategy_id = ? and version = ?
        """,
        (STRATEGY_ID, STRATEGY_VERSION),
    ).fetchone()
    policy = get_strategy_policy(conn)
    if definition is None or version is None:
        raise RuntimeError(f"Missing strategy metadata for {STRATEGY_ID}:{STRATEGY_VERSION}")
    return {
        "kind": "strategy_report",
        "strategy_id": str(definition["strategy_id"]),
        "name": str(definition["name"]),
        "type": str(definition["type"]),
        "market_scope": str(definition["market_scope"]),
        "description": str(definition["description"] or ""),
        "version": str(version["version"]),
        "enabled": bool(version["enabled"]),
        "parameters": json.loads(str(version["parameters_json"])),
        "rules": json.loads(str(version["rules_json"])),
        "policy": {
            "allowed_universe_id": str(policy["allowed_universe_id"]),
            "allowed_asset_type": str(policy["allowed_asset_type"]),
            "allowed_market_scope": str(policy["allowed_market_scope"]),
            "require_latest_sync": bool(policy["require_latest_sync"]),
            "require_recent_backtest_for_live": bool(policy["require_recent_backtest_for_live"]),
            "max_backtest_staleness_days": int(policy["max_backtest_staleness_days"]),
        },
    }


def get_strategy_requirements(conn: sqlite3.Connection, strategy_id: str = STRATEGY_ID, version: str = STRATEGY_VERSION) -> dict[str, Any]:
    version_row = conn.execute(
        """
        select parameters_json
        from strategy_versions
        where strategy_id = ? and version = ?
        """,
        (strategy_id, version),
    ).fetchone()
    if version_row is None:
        raise RuntimeError(f"Missing strategy version metadata for {strategy_id}:{version}")
    parameters = json.loads(str(version_row["parameters_json"]))
    ma_window = int(parameters.get("ma_window", 150))
    return {
        "strategy_id": strategy_id,
        "version": version,
        "ma_window": ma_window,
        "signal": {
            "min_total_bars": ma_window + 1,
            "min_post_warmup_bars": 2,
            "warmup_bars": ma_window,
        },
        "backtest": {
            "min_total_bars": ma_window + 1,
            "min_post_warmup_bars": 3,
            "warmup_bars": ma_window,
        },
    }


def build_strategy_runtime_deps() -> Strategy150maDeps:
    return Strategy150maDeps(
        strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION,
        ensure_symbol_allowed=ensure_symbol_allowed,
        get_strategy_requirements=get_strategy_requirements,
        get_strategy_policy=get_strategy_policy,
        list_universe_symbols=list_universe_symbols,
        load_symbol_bars=load_symbol_bars,
        maybe_render_backtest_html=maybe_render_backtest_html,
        require_latest_sync=require_latest_sync,
        require_recent_backtest=require_recent_backtest,
        utc_now=utc_now,
    )


def build_strategy_data_check(
    conn: sqlite3.Connection,
    symbol: str,
    purpose: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    return strategy_build_strategy_data_check(
        conn,
        build_strategy_runtime_deps(),
        symbol=symbol,
        purpose=purpose,
        start_date=start_date,
        end_date=end_date,
    )


def compute_signal_150ma(conn: sqlite3.Connection, symbol: str, trade_date: str | None = None) -> dict[str, Any]:
    return strategy_compute_signal_150ma(conn, build_strategy_runtime_deps(), symbol, trade_date=trade_date)


def build_strategy_daily_report(conn: sqlite3.Connection, trade_date: str | None = None) -> dict[str, Any]:
    target_trade_date = trade_date or get_latest_market_trade_date(conn)
    symbols = list_universe_symbols(conn)
    buy: list[dict[str, Any]] = []
    sell: list[dict[str, Any]] = []
    hold_count = 0
    skipped: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for item in symbols:
        try:
            signal = compute_signal_150ma(conn, item["symbol"], trade_date=target_trade_date)
            if signal["kind"] != "signal_report":
                skipped.append(signal)
                continue
            summary_row = {
                "symbol": signal["symbol"],
                "name": signal["name"],
                "sector_name": signal["sector_name"],
                "trade_date": signal["trade_date"],
                "close": signal["close"],
                "ma150": signal["ma150"],
                "action": signal["action"],
                "target_position": signal["target_position"],
                "rationale": signal["rationale"],
            }
            if signal["action"] == "buy":
                buy.append(summary_row)
            elif signal["action"] == "sell":
                sell.append(summary_row)
            else:
                hold_count += 1
        except Exception as exc:
            failures.append({"symbol": item["symbol"], "message": str(exc)})

    return {
        "kind": "strategy_daily_report",
        "strategy_id": STRATEGY_ID,
        "version": STRATEGY_VERSION,
        "trade_date": target_trade_date,
        "status": "completed" if not failures else "partial",
        "total_symbols": len(symbols),
        "buy_count": len(buy),
        "sell_count": len(sell),
        "hold_count": hold_count,
        "skipped_count": len(skipped),
        "failed_count": len(failures),
        "buy_list": buy,
        "sell_list": sell,
        "skipped": skipped,
        "failures": failures,
    }


def maybe_render_backtest_html(report: dict[str, Any], output_path: str | None) -> str | None:
    if not output_path:
        return None

    try:
        from pyecharts import options as opts
        from pyecharts.charts import Grid, Line
    except ImportError as exc:
        return render_basic_backtest_html(report, output_path, reason=str(exc))

    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    trade_dates = [point["trade_date"] for point in report["equity_curve"]]
    close_values = [point["close"] for point in report["equity_curve"]]
    ma_values = [point["ma150"] for point in report["equity_curve"]]
    equity_values = [point["equity"] for point in report["equity_curve"]]

    price_line = (
        Line()
        .add_xaxis(trade_dates)
        .add_yaxis("Close", close_values, is_smooth=False, is_symbol_show=False)
        .add_yaxis("MA150", ma_values, is_smooth=False, is_symbol_show=False)
        .set_global_opts(
            title_opts=opts.TitleOpts(title=f"{report['symbol']} {report['name']} 150MA Backtest"),
            legend_opts=opts.LegendOpts(pos_top="4%"),
            datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100)],
            xaxis_opts=opts.AxisOpts(type_="category"),
            yaxis_opts=opts.AxisOpts(type_="value"),
        )
    )

    equity_line = (
        Line()
        .add_xaxis(trade_dates)
        .add_yaxis("Equity", equity_values, is_smooth=False, is_symbol_show=False)
        .set_global_opts(
            legend_opts=opts.LegendOpts(is_show=False),
            xaxis_opts=opts.AxisOpts(type_="category"),
            yaxis_opts=opts.AxisOpts(type_="value"),
        )
    )

    grid = Grid(init_opts=opts.InitOpts(width="1440px", height="900px"))
    grid.add(price_line, grid_opts=opts.GridOpts(pos_left="6%", pos_right="4%", pos_top="10%", height="38%"))
    grid.add(equity_line, grid_opts=opts.GridOpts(pos_left="6%", pos_right="4%", pos_top="56%", height="28%"))
    grid.render(str(path))
    return str(path)


def render_basic_backtest_html(report: dict[str, Any], output_path: str, reason: str) -> str:
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        f"<tr><td>{point['trade_date']}</td><td>{point['close']:.4f}</td><td>{point['ma150']:.4f}</td><td>{point['equity']:.2f}</td></tr>"
        for point in report["equity_curve"][-30:]
    )
    trades = "\n".join(
        f"<tr><td>{trade['date']}</td><td>{trade['action']}</td><td>{trade['price']:.4f}</td></tr>"
        for trade in report["trades"]
    ) or "<tr><td colspan='3'>No completed trades</td></tr>"
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{report['symbol']} backtest report</title>
  <style>
    body {{ font-family: sans-serif; margin: 24px; color: #111827; }}
    table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; text-align: left; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .card {{ border: 1px solid #d1d5db; border-radius: 8px; padding: 12px; background: #f9fafb; }}
    .note {{ color: #92400e; }}
  </style>
</head>
<body>
  <h1>{report['symbol']} {report['name']} 150MA Backtest</h1>
  <p class="note">pyecharts unavailable, generated fallback HTML report. Reason: {reason}</p>
  <div class="grid">
    <div class="card"><strong>Total Return</strong><div>{report['total_return']:.2%}</div></div>
    <div class="card"><strong>Annual Return</strong><div>{report['annual_return']:.2%}</div></div>
    <div class="card"><strong>Max Drawdown</strong><div>{report['max_drawdown']:.2%}</div></div>
    <div class="card"><strong>Win Rate</strong><div>{report['win_rate']:.2%}</div></div>
  </div>
  <h2>Trades</h2>
  <table>
    <thead><tr><th>Date</th><th>Action</th><th>Price</th></tr></thead>
    <tbody>{trades}</tbody>
  </table>
  <h2>Recent Equity Points</h2>
  <table>
    <thead><tr><th>Trade Date</th><th>Close</th><th>MA150</th><th>Equity</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>"""
    path.write_text(html, encoding="utf-8")
    return str(path)


def run_backtest_150ma(
    conn: sqlite3.Connection,
    symbol: str,
    start_date: str,
    end_date: str,
    capital: float,
    report_path: str | None,
    report_html: str | None,
) -> dict[str, Any]:
    return strategy_run_backtest_150ma(
        conn,
        build_strategy_runtime_deps(),
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        capital=capital,
        report_path=report_path,
        report_html=report_html,
    )


def create_trade_plan(conn: sqlite3.Connection, symbol: str, mode: str) -> dict[str, Any]:
    return strategy_create_trade_plan(conn, build_strategy_runtime_deps(), symbol=symbol, mode=mode)


def batch_signal_150ma(conn: sqlite3.Connection, trade_date: str | None = None) -> dict[str, Any]:
    return strategy_batch_signal_150ma(conn, build_strategy_runtime_deps(), trade_date=trade_date)


def batch_backtest_150ma(conn: sqlite3.Connection, start_date: str, end_date: str, capital: float) -> dict[str, Any]:
    return strategy_batch_backtest_150ma(
        conn,
        build_strategy_runtime_deps(),
        start_date=start_date,
        end_date=end_date,
        capital=capital,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stock agent CLI for OpenClaw.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-db")
    init_parser.add_argument("--db", required=True)

    discover_parser = subparsers.add_parser("discover-industry-etfs")
    discover_parser.add_argument("--db")
    discover_parser.add_argument("--keywords")
    discover_parser.add_argument("--output")
    discover_parser.add_argument("--write-universe", action="store_true")

    seed_parser = subparsers.add_parser("seed-universe")
    seed_parser.add_argument("--db", required=True)
    seed_parser.add_argument("--csv", required=True)

    bootstrap_db_parser = subparsers.add_parser("bootstrap-db")
    bootstrap_db_parser.add_argument("--db", required=True)
    bootstrap_db_parser.add_argument("--csv")

    demo_parser = subparsers.add_parser("seed-demo-bars")
    demo_parser.add_argument("--db", required=True)
    demo_parser.add_argument("--start", default="2024-01-02")
    demo_parser.add_argument("--days", type=int, default=220)
    demo_parser.add_argument("--trend", choices=["bullish", "bearish", "range", "signal-buy", "signal-sell"], default="bullish")
    demo_parser.add_argument("--no-sync-record", action="store_true")

    bootstrap_parser = subparsers.add_parser("bootstrap-history")
    bootstrap_parser.add_argument("--db", required=True)
    bootstrap_parser.add_argument("--start", required=True)
    bootstrap_parser.add_argument("--end", default=date.today().isoformat())

    range_parser = subparsers.add_parser("sync-range")
    range_parser.add_argument("--db", required=True)
    range_parser.add_argument("--start", required=True)
    range_parser.add_argument("--end", required=True)

    coverage_parser = subparsers.add_parser("coverage-report")
    coverage_parser.add_argument("--db", required=True)
    coverage_parser.add_argument("--start", required=True)
    coverage_parser.add_argument("--end", required=True)

    prune_parser = subparsers.add_parser("prune-empty-data")
    prune_parser.add_argument("--db", required=True)
    prune_parser.add_argument("--start", required=True)
    prune_parser.add_argument("--end", required=True)
    prune_parser.add_argument("--csv")

    audit_universe_parser = subparsers.add_parser("audit-universe")
    audit_universe_parser.add_argument("--db", required=True)

    prune_non_industry_parser = subparsers.add_parser("prune-non-industry")
    prune_non_industry_parser.add_argument("--db", required=True)
    prune_non_industry_parser.add_argument("--csv")

    sync_parser = subparsers.add_parser("sync-daily")
    sync_parser.add_argument("--db", required=True)
    sync_parser.add_argument("--trade-date")

    sync_status_parser = subparsers.add_parser("sync-status")
    sync_status_parser.add_argument("--db", required=True)

    strategy_daily_parser = subparsers.add_parser("strategy-daily-report")
    strategy_daily_parser.add_argument("--db", required=True)
    strategy_daily_parser.add_argument("--trade-date")

    movers_parser = subparsers.add_parser("top-movers")
    movers_parser.add_argument("--db", required=True)
    movers_parser.add_argument("--trade-date")
    movers_parser.add_argument("--top", type=int, default=10)

    search_parser = subparsers.add_parser("search-etf")
    search_parser.add_argument("--db", required=True)
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--limit", type=int, default=10)

    latest_price_parser = subparsers.add_parser("latest-price")
    latest_price_parser.add_argument("--db", required=True)
    latest_price_parser.add_argument("--symbol", required=True)

    detail_parser = subparsers.add_parser("etf-detail")
    detail_parser.add_argument("--db", required=True)
    detail_parser.add_argument("--symbol", required=True)
    detail_parser.add_argument("--start")
    detail_parser.add_argument("--end")
    detail_parser.add_argument("--recent-bars", type=int, default=20)

    technical_indicators_parser = subparsers.add_parser("technical-indicators")
    technical_indicators_parser.add_argument("--db", required=True)
    technical_indicators_parser.add_argument("--symbol", required=True)
    technical_indicators_parser.add_argument("--start")
    technical_indicators_parser.add_argument("--end")
    technical_indicators_parser.add_argument("--recent-bars", type=int, default=20)

    technical_analysis_parser = subparsers.add_parser("technical-analysis")
    technical_analysis_parser.add_argument("--db", required=True)
    technical_analysis_parser.add_argument("--symbol", required=True)
    technical_analysis_parser.add_argument("--start")
    technical_analysis_parser.add_argument("--end")
    technical_analysis_parser.add_argument("--recent-bars", type=int, default=20)
    technical_analysis_parser.add_argument("--include-series", action="store_true")

    strategy_get_parser = subparsers.add_parser("strategy-get")
    strategy_get_parser.add_argument("--db", required=True)

    data_check_parser = subparsers.add_parser("strategy-data-check")
    data_check_parser.add_argument("--db", required=True)
    data_check_parser.add_argument("--symbol", required=True)
    data_check_parser.add_argument("--purpose", choices=["signal", "backtest"], required=True)
    data_check_parser.add_argument("--start")
    data_check_parser.add_argument("--end")

    signal_parser = subparsers.add_parser("signal-150ma")
    signal_parser.add_argument("--db", required=True)
    signal_parser.add_argument("--symbol", required=True)

    batch_signal_parser = subparsers.add_parser("batch-signal-150ma")
    batch_signal_parser.add_argument("--db", required=True)
    batch_signal_parser.add_argument("--trade-date")

    backtest_parser = subparsers.add_parser("backtest-150ma")
    backtest_parser.add_argument("--db", required=True)
    backtest_parser.add_argument("--symbol", required=True)
    backtest_parser.add_argument("--start", required=True)
    backtest_parser.add_argument("--end", required=True)
    backtest_parser.add_argument("--capital", type=float, default=100000.0)
    backtest_parser.add_argument("--report")
    backtest_parser.add_argument("--report-html")

    batch_backtest_parser = subparsers.add_parser("batch-backtest-150ma")
    batch_backtest_parser.add_argument("--db", required=True)
    batch_backtest_parser.add_argument("--start", required=True)
    batch_backtest_parser.add_argument("--end", required=True)
    batch_backtest_parser.add_argument("--capital", type=float, default=100000.0)

    plan_parser = subparsers.add_parser("trade-plan-150ma")
    plan_parser.add_argument("--db", required=True)
    plan_parser.add_argument("--symbol", required=True)
    plan_parser.add_argument("--mode", default="paper")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    conn = connect_db(args.db)
    try:
        if args.command == "init-db":
            init_db(conn)
            result = {"kind": "init_report", "status": "ok", "db": args.db}
        elif args.command == "discover-industry-etfs":
            init_db(conn)
            keywords = parse_keyword_list(args.keywords)
            rows = discover_industry_etfs(keywords)
            output_path: str | None = None
            if args.output:
                output_path = write_candidate_csv(args.output, rows)
            seed_report: dict[str, Any] | None = None
            if args.write_universe:
                seed_report = seed_universe_rows(conn, rows)
            result = {
                "kind": "industry_etf_discovery",
                "keywords": keywords,
                "count": len(rows),
                "output_path": output_path,
                "seed_report": seed_report,
                "candidates": rows,
            }
        elif args.command == "seed-universe":
            init_db(conn)
            result = seed_universe(conn, args.csv)
        elif args.command == "bootstrap-db":
            result = bootstrap_db(conn, db_path=args.db, csv_path=args.csv)
        elif args.command == "seed-demo-bars":
            init_db(conn)
            result = seed_demo_bars(
                conn,
                start_date=args.start,
                days=args.days,
                trend=args.trend,
                record_sync=not args.no_sync_record,
            )
        elif args.command == "bootstrap-history":
            init_db(conn)
            result = bootstrap_history(conn, start_date=args.start, end_date=args.end)
        elif args.command == "sync-range":
            init_db(conn)
            result = bootstrap_history(conn, start_date=args.start, end_date=args.end)
        elif args.command == "coverage-report":
            init_db(conn)
            result = get_range_coverage_report(conn, start_date=args.start, end_date=args.end)
        elif args.command == "prune-empty-data":
            init_db(conn)
            result = prune_empty_universe_members(conn, start_date=args.start, end_date=args.end, csv_path=args.csv)
        elif args.command == "audit-universe":
            init_db(conn)
            result = audit_universe_members(conn)
        elif args.command == "prune-non-industry":
            init_db(conn)
            result = prune_non_industry_universe_members(conn, csv_path=args.csv)
        elif args.command == "sync-daily":
            init_db(conn)
            result = sync_daily(conn, trade_date=args.trade_date)
        elif args.command == "sync-status":
            init_db(conn)
            result = get_sync_status_report(conn)
        elif args.command == "strategy-daily-report":
            init_db(conn)
            result = build_strategy_daily_report(conn, trade_date=args.trade_date)
        elif args.command == "top-movers":
            init_db(conn)
            result = get_top_etf_movers_report(conn, trade_date=args.trade_date, top_n=args.top)
        elif args.command == "search-etf":
            init_db(conn)
            result = search_etfs(conn, query=args.query, limit=args.limit)
        elif args.command == "latest-price":
            init_db(conn)
            result = get_etf_latest_price(conn, symbol=args.symbol)
        elif args.command == "etf-detail":
            init_db(conn)
            result = get_etf_detail(
                conn,
                symbol=args.symbol,
                start_date=args.start,
                end_date=args.end,
                recent_bars=args.recent_bars,
            )
        elif args.command == "technical-indicators":
            init_db(conn)
            result = get_technical_indicators_report(
                conn,
                symbol=args.symbol,
                start_date=args.start,
                end_date=args.end,
                recent_bars=args.recent_bars,
            )
        elif args.command == "technical-analysis":
            init_db(conn)
            result = get_technical_analysis_report(
                conn,
                symbol=args.symbol,
                start_date=args.start,
                end_date=args.end,
                recent_bars=args.recent_bars,
                include_series=args.include_series,
            )
        elif args.command == "strategy-get":
            init_db(conn)
            result = get_strategy_report(conn)
        elif args.command == "strategy-data-check":
            init_db(conn)
            result = build_strategy_data_check(
                conn,
                symbol=args.symbol,
                purpose=args.purpose,
                start_date=args.start,
                end_date=args.end,
            )
        elif args.command == "signal-150ma":
            init_db(conn)
            result = compute_signal_150ma(conn, args.symbol)
        elif args.command == "batch-signal-150ma":
            init_db(conn)
            result = batch_signal_150ma(conn, trade_date=args.trade_date)
        elif args.command == "backtest-150ma":
            init_db(conn)
            result = run_backtest_150ma(
                conn,
                symbol=args.symbol,
                start_date=args.start,
                end_date=args.end,
                capital=args.capital,
                report_path=args.report,
                report_html=args.report_html,
            )
        elif args.command == "batch-backtest-150ma":
            init_db(conn)
            result = batch_backtest_150ma(conn, start_date=args.start, end_date=args.end, capital=args.capital)
        elif args.command == "trade-plan-150ma":
            init_db(conn)
            result = create_trade_plan(conn, symbol=args.symbol, mode=args.mode)
        else:
            raise RuntimeError(f"Unsupported command: {args.command}")
    except Exception as exc:
        die(str(exc))
    finally:
        conn.close()

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
