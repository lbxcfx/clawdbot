from __future__ import annotations

from typing import Any

from indicators_config import (
    ADX_WINDOW,
    ATR_WINDOW,
    BOLL_STD,
    BOLL_WINDOW,
    EMA_WINDOWS,
    KDJ_WINDOW,
    MACD_FAST,
    MACD_SIGNAL,
    MACD_SLOW,
    MA_WINDOWS,
    RSI_WINDOWS,
)


def load_pandas():
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required. Install requirements.txt first.") from exc
    return pd


def load_talib():
    try:
        import talib
    except ImportError:
        return None
    return talib


def _copy_df(df: Any):
    return df.copy()


def compute_ma(df: Any, windows: list[int] | None = None):
    result = _copy_df(df)
    for window in windows or MA_WINDOWS:
        result[f"ma_{window}"] = result["close"].rolling(window).mean()
    return result


def compute_ema(df: Any, windows: list[int] | None = None):
    result = _copy_df(df)
    talib = load_talib()
    close_values = result["close"].astype(float)
    for window in windows or EMA_WINDOWS:
        if talib is not None:
            result[f"ema_{window}"] = talib.EMA(close_values, timeperiod=window)
        else:
            result[f"ema_{window}"] = close_values.ewm(span=window, adjust=False).mean()
    return result


def compute_macd(df: Any, fast: int = MACD_FAST, slow: int = MACD_SLOW, signal: int = MACD_SIGNAL):
    result = _copy_df(df)
    talib = load_talib()
    close_values = result["close"].astype(float)
    if talib is not None:
        dif, dea, hist = talib.MACD(close_values, fastperiod=fast, slowperiod=slow, signalperiod=signal)
    else:
        ema_fast = close_values.ewm(span=fast, adjust=False).mean()
        ema_slow = close_values.ewm(span=slow, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal, adjust=False).mean()
        hist = dif - dea
    result["macd_dif"] = dif
    result["macd_dea"] = dea
    result["macd_hist"] = hist
    return result


def compute_rsi(df: Any, windows: list[int] | None = None):
    result = _copy_df(df)
    talib = load_talib()
    close_values = result["close"].astype(float)
    for window in windows or RSI_WINDOWS:
        if talib is not None:
            result[f"rsi_{window}"] = talib.RSI(close_values, timeperiod=window)
            continue
        delta = close_values.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
        avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
        rs = avg_gain / avg_loss
        result[f"rsi_{window}"] = 100 - (100 / (1 + rs))
    return result


def compute_kdj(df: Any, window: int = KDJ_WINDOW):
    pd = load_pandas()
    result = _copy_df(df)
    low_n = result["low"].rolling(window).min()
    high_n = result["high"].rolling(window).max()
    denominator = (high_n - low_n).replace(0, pd.NA)
    rsv = ((result["close"] - low_n) / denominator) * 100
    result["kdj_k"] = rsv.ewm(com=2, adjust=False).mean()
    result["kdj_d"] = result["kdj_k"].ewm(com=2, adjust=False).mean()
    result["kdj_j"] = 3 * result["kdj_k"] - 2 * result["kdj_d"]
    return result


def compute_boll(df: Any, window: int = BOLL_WINDOW, num_std: int = BOLL_STD):
    result = _copy_df(df)
    talib = load_talib()
    close_values = result["close"].astype(float)
    if talib is not None:
        upper, middle, lower = talib.BBANDS(
            close_values,
            timeperiod=window,
            nbdevup=num_std,
            nbdevdn=num_std,
            matype=0,
        )
    else:
        middle = close_values.rolling(window).mean()
        std = close_values.rolling(window).std(ddof=0)
        upper = middle + std * num_std
        lower = middle - std * num_std
    result["boll_mid"] = middle
    result["boll_upper"] = upper
    result["boll_lower"] = lower
    result["boll_width"] = (upper - lower) / middle
    return result


def compute_atr(df: Any, window: int = ATR_WINDOW):
    pd = load_pandas()
    result = _copy_df(df)
    talib = load_talib()
    high_values = result["high"].astype(float)
    low_values = result["low"].astype(float)
    close_values = result["close"].astype(float)
    if talib is not None:
        atr = talib.ATR(high_values, low_values, close_values, timeperiod=window)
    else:
        prev_close = close_values.shift(1)
        tr_components = pd.concat(
            [
                high_values - low_values,
                (high_values - prev_close).abs(),
                (low_values - prev_close).abs(),
            ],
            axis=1,
        )
        true_range = tr_components.max(axis=1)
        atr = true_range.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    result[f"atr_{window}"] = atr
    return result


def compute_obv(df: Any):
    result = _copy_df(df)
    talib = load_talib()
    close_values = result["close"].astype(float)
    volume_values = result["volume"].astype(float)
    if talib is not None:
        result["obv"] = talib.OBV(close_values, volume_values)
        return result
    direction = close_values.diff().fillna(0.0)
    signed_volume = volume_values.where(direction >= 0, -volume_values)
    signed_volume = signed_volume.where(direction != 0, 0.0)
    result["obv"] = signed_volume.cumsum()
    return result


def compute_adx(df: Any, window: int = ADX_WINDOW):
    pd = load_pandas()
    result = _copy_df(df)
    talib = load_talib()
    high_values = result["high"].astype(float)
    low_values = result["low"].astype(float)
    close_values = result["close"].astype(float)
    if talib is not None:
        result[f"adx_{window}"] = talib.ADX(high_values, low_values, close_values, timeperiod=window)
        return result

    up_move = high_values.diff()
    down_move = -low_values.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    prev_close = close_values.shift(1)
    true_range = pd.concat(
        [
            high_values - low_values,
            (high_values - prev_close).abs(),
            (low_values - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / window, adjust=False, min_periods=window).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / window, adjust=False, min_periods=window).mean() / atr
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di)) * 100
    result[f"adx_{window}"] = dx.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    return result


def compute_indicators(df: Any, indicator_set: list[str] | None = None):
    selected = set(indicator_set or ["ma", "ema", "macd", "rsi", "kdj", "boll", "atr", "obv", "adx"])
    result = _copy_df(df)

    if "ma" in selected:
        result = compute_ma(result)
    if "ema" in selected:
        result = compute_ema(result)
    if "macd" in selected:
        result = compute_macd(result)
    if "rsi" in selected:
        result = compute_rsi(result)
    if "kdj" in selected:
        result = compute_kdj(result)
    if "boll" in selected:
        result = compute_boll(result)
    if "atr" in selected:
        result = compute_atr(result)
    if "obv" in selected:
        result = compute_obv(result)
    if "adx" in selected:
        result = compute_adx(result)
    return result
