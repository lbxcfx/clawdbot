from __future__ import annotations

MA_WINDOWS = [5, 10, 20, 60, 150]
EMA_WINDOWS = [12, 26]
RSI_WINDOWS = [6, 14]

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

KDJ_WINDOW = 9

BOLL_WINDOW = 20
BOLL_STD = 2

ATR_WINDOW = 14
ADX_WINDOW = 14

TECHNICAL_INDICATOR_FIELDS = [
    "ma_5",
    "ma_10",
    "ma_20",
    "ma_60",
    "ma_150",
    "ema_12",
    "ema_26",
    "macd_dif",
    "macd_dea",
    "macd_hist",
    "rsi_6",
    "rsi_14",
    "kdj_k",
    "kdj_d",
    "kdj_j",
    "boll_mid",
    "boll_upper",
    "boll_lower",
    "boll_width",
    "atr_14",
    "obv",
    "adx_14",
]
