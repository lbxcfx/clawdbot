from __future__ import annotations

import math
from typing import Any

from indicators import compute_indicators
from indicators_config import TECHNICAL_INDICATOR_FIELDS


def _sanitize_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def build_technical_dataframe(df: Any, indicator_set: list[str] | None = None):
    return compute_indicators(df, indicator_set=indicator_set)


def build_latest_indicator_snapshot(df: Any) -> dict[str, Any]:
    if len(df) == 0:
        raise RuntimeError("No rows available for technical analysis.")
    last_row = df.iloc[-1]
    return {
        field: _sanitize_value(last_row[field]) for field in TECHNICAL_INDICATOR_FIELDS if field in df.columns
    }


def build_recent_indicator_series(df: Any, recent_bars: int) -> list[dict[str, Any]]:
    rows = df.tail(max(recent_bars, 1))
    payload: list[dict[str, Any]] = []
    for _, row in rows.iterrows():
        item = {
            "trade_date": row["trade_date"].strftime("%Y-%m-%d"),
        }
        for field in TECHNICAL_INDICATOR_FIELDS:
            if field in df.columns:
                item[field] = _sanitize_value(row[field])
        payload.append(item)
    return payload


def build_technical_payload(
    df: Any,
    recent_bars: int = 20,
    include_series: bool = False,
    indicator_set: list[str] | None = None,
) -> dict[str, Any]:
    technical_df = build_technical_dataframe(df, indicator_set=indicator_set)
    latest_row = technical_df.iloc[-1]
    payload = {
        "kind": "technical_analysis",
        "trade_date": latest_row["trade_date"].strftime("%Y-%m-%d"),
        "indicators": build_latest_indicator_snapshot(technical_df),
    }
    if include_series:
        payload["series"] = build_recent_indicator_series(technical_df, recent_bars=recent_bars)
    return payload
