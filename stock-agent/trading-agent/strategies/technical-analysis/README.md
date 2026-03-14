# technical-analysis

这是 `trading-agent` 的技术分析能力说明目录。

当前职责：

- 统一计算通用技术指标
- 向策略层提供可复用的指标结果
- 向 CLI、插件和详情接口提供标准化技术分析输出

当前已支持指标：

- MA
- EMA
- MACD
- RSI
- KDJ
- BOLL
- ATR
- OBV
- ADX

指标命名规范：

- MA：`ma_5`、`ma_10`、`ma_20`、`ma_60`、`ma_150`
- EMA：`ema_12`、`ema_26`
- MACD：`macd_dif`、`macd_dea`、`macd_hist`
- RSI：`rsi_6`、`rsi_14`
- KDJ：`kdj_k`、`kdj_d`、`kdj_j`
- BOLL：`boll_mid`、`boll_upper`、`boll_lower`、`boll_width`
- ATR：`atr_14`
- OBV：`obv`
- ADX：`adx_14`

扩展约束：

- 技术分析能力与策略解耦
- 策略只能读取技术指标结果，不应重复计算
- 后续形态识别、趋势识别、波动识别统一扩展在技术分析模块下
- 标准化特征输出也应从技术分析模块产出
