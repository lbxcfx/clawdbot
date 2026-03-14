# trading-agent 扩展说明

本文档约束 `trading-agent` 后续的扩展方式，目标是保证：

- 业务实现可维护
- agent 调用链路清晰
- 新策略可平滑增加
- prompt、skill、代码、数据边界明确

## 一、总体原则

不要把真正的业务实现长期塞进 `SKILL.md`。

职责拆分如下：

- 运行时层：放正式代码、数据库、CSV、schema、命令入口、测试
- skill 层：放行为约束、调用顺序、风控要求、输出格式、研究原则
- workspace 根文件：放 agent 角色、用户偏好、工具说明和长期约束

## 二、什么放在 skills 里

适合放在 `skills/` 里的内容：

- 调用顺序
- 风控规则
- 输出格式要求
- 某类任务的分析方法
- 什么时候用哪个工具
- 某个策略的使用边界和解读规则

只有当某个 skill 确实需要独立脚本、模板或参考资料时，才给它增加：

- `scripts/`
- `references/`
- `assets/`

如果一个 skill 只是规则层，就只有 `SKILL.md`，这是合理的。

推荐按两类组织：

- 开放式 workflow skill：处理问法多变、路径可分支的问题
- 固定 workflow skill：处理必须一致执行、必须可复核的问题

示例：

- 开放式 workflow：`etf-quote-workflow`
- 固定 workflow：`strategy-validation-workflow`

## 三、什么不放在 skills 里

下面这些不应只存在于 `skills/`：

- 真实行情计算逻辑
- 数据库存取逻辑
- 指标计算实现
- 回测主流程
- 交易计划生成主流程
- 数据同步实现

这些都必须放在 `stock-agent/trading-agent/` 的正式运行时代码里。

## 四、新策略如何增加

新增一个策略时，至少要同时增加四部分：

1. 运行时实现
2. 策略说明或 skill
3. 测试
4. 如有需要，数据库字段或输出 schema

推荐结构：

```text
stock-agent/trading-agent/
  scripts/
  data/
  references/
  strategies/
    strategy-150ma-v1/
      README.md
      params.json
    strategy-xxx-v1/
      README.md
      params.json
```

同时在 workspace `skills/` 中增加对应规则层 skill，例如：

```text
~/.openclaw/workspace-trading-agent/skills/
  etf-quote-workflow/
    SKILL.md
  strategy-validation-workflow/
    SKILL.md
  strategy-150ma-review/
    SKILL.md
  strategy-xxx-review/
    SKILL.md
```

## 五、推荐落地方式

对于每个新策略：

- 运行时层负责“算”
- skill 层负责“怎么用、怎么解释、怎么控风险”

不要反过来。

## 七、技术指标模块扩展约束

技术指标模块是 `trading-agent` 的独立能力层，放在 `scripts/indicators.py` 与 `scripts/technical_analysis.py`。

约束如下：

- 技术指标实现必须放 runtime，不放 skill
- 策略只能消费技术指标结果，不应在策略内部重复计算均线或其他指标
- `strategy-150MA:v1` 已改为消费 `ma_150`
- 后续形态识别、趋势识别、波动识别统一扩展到 `technical_analysis.py`
- 如未来要做特征缓存，应新增独立缓存层，不污染策略逻辑

## 六、当前建议

当前 `trading-agent` 已经有这些规则型 skills：

- `trading-workflow`
- `trading-risk-policy`
- `trading-output-schema`
- `backtest-review`
- `sql-read-policy`
- `akshare-research`
- `etf-quote-workflow`
- `strategy-validation-workflow`

这些 skill 只有 `SKILL.md` 是合理的，因为它们现在承担的是规则职责，不是业务实现职责。

如果以后新增下面这些能力，就建议给对应 skill 加 `scripts/`：

- 指标结果格式转换
- 策略报告模板生成
- 批量结果汇总
- 只属于某个策略的轻量辅助脚本

但“主交易逻辑”依然应放在 `stock-agent/trading-agent/` 正式运行时中。
