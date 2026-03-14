# trading-agent 开发指南

本文档说明如何基于当前仓库开发一个新的 OpenClaw agent，尤其适用于像 `trading-agent` 这样的正式业务 agent。

## 一、先明确边界

开发新 agent 之前，先把下面三层分清：

- workspace 根文件：定义 agent 身份、行为边界、用户偏好、工具使用原则
- skills：定义可复用 workflow、风控规则、输出结构、任务分支
- runtime：定义真实业务实现、数据库、脚本、配置、测试

不要把真实业务逻辑长期写在 `AGENTS.md` 或 `SKILL.md` 里。

## 二、目录组织建议

推荐按下面结构组织：

```text
stock-agent/
  <new-agent>/
    data/
    references/
    scripts/
    strategies/
    README.md
    requirements.txt
    EXTENSIBILITY.md
```

同时为真实 workspace 准备根文件和 skills：

```text
~/.openclaw/workspace-<agent-id>/
  AGENTS.md
  SOUL.md
  USER.md
  IDENTITY.md
  TOOLS.md
  BOOTSTRAP.md
  HEARTBEAT.md
  skills/
```

## 三、开发顺序

建议按下面顺序开发：

1. 定义 agent 目标和范围
2. 设计工具原子能力
3. 再设计 workflow skill
4. 最后补 workspace 根文件

顺序不要反过来。

先有稳定工具，再写 prompt 和 skill，才能保证调用稳定。

## 四、如何定义一个新 agent

### 1. 定义业务范围

至少要明确：

- 这个 agent 处理什么问题
- 不处理什么问题
- 数据来源是什么
- 数据存储在哪里
- 对外暴露哪些工具动作

例如 `trading-agent` 当前范围是：

- 场内行业 ETF
- 日线
- 本地数据库优先
- 先检索，再查详情，再生成结论

### 2. 定义 runtime 原子能力

runtime 里的每个动作都应该尽量单一、清晰、可组合，例如：

- `search_etf`
- `etf_detail`
- `sync_status`
- `top_movers`
- `strategy_daily_report`

原则：

- 一个动作只做一件核心事
- 输入输出要稳定
- 返回结构要便于后续 workflow 复用

### 3. 定义 workflow skill

skill 负责组织调用顺序，不负责真正计算。

建议把 skill 分两类：

- 开放式 workflow：适合问法多变的问题
- 固定 workflow：适合必须保持一致性的流程

例如：

- `etf-quote-workflow`：开放式
- `strategy-validation-workflow`：固定流程

### 4. 定义 workspace 根文件

根文件的职责建议如下：

- `AGENTS.md`：总规则、边界、总 workflow 入口
- `SOUL.md`：语气、角色、风格
- `USER.md`：用户偏好
- `IDENTITY.md`：agent 的业务定位
- `TOOLS.md`：工具入口和调用约定
- `BOOTSTRAP.md`：首次启动时的初始化说明
- `HEARTBEAT.md`：周期任务说明

## 五、工具设计注意事项

### 1. 不要只暴露过于底层的动作

例如只暴露 `etf_detail(symbol)`，但不提供 `search_etf(query)`，模型就容易卡在“缺 symbol”。

正确做法是同时提供：

- 解析动作
- 明细动作
- 状态动作

### 2. 工具契约必须和 prompt 对齐

如果 prompt 写“先检索再查详情”，工具就必须真的提供检索动作。

如果工具做不到，模型就会退回自由发挥。

### 3. 返回结构要稳定

建议固定返回：

- `kind`
- 关键标识字段
- 时间字段
- 状态字段

这样 skill 和 agent 更容易复用结果。

## 六、skills 设计注意事项

### 1. skill 只写规则，不写主逻辑

合理：

- 什么时候先 `search_etf`
- 多命中如何处理
- 输出字段怎么组织

不合理：

- 在 `SKILL.md` 里塞业务 SQL
- 在 `SKILL.md` 里塞完整计算实现

### 2. skill 要按问题类型命名

推荐：

- `xxx-quote-workflow`
- `xxx-research-workflow`
- `xxx-validation-workflow`

不要用过于模糊的名字。

### 3. 强一致流程要单独抽出来

比如“测试一个新的策略方案”，必须单独做固定 workflow，不要混进通用 skill。

## 七、数据与配置注意事项

### 1. 代码、数据、CSV、配置要收口

不要让正式 agent 还依赖：

- `local-prototype`
- 临时路径
- 手工复制数据
- workspace 外的未声明资产

正式运行时必须明确：

- 代码路径
- 数据库路径
- 初始 CSV 路径
- 插件配置路径

### 2. 服务启动后要能自举

建议至少具备：

- 数据库不存在时自动初始化
- 候选池为空时自动导入基础 CSV
- 状态查询可直接验证库是否可用

### 3. 配置变更后要重启 Gateway

尤其是插件路径、插件配置、workspace、工具清单发生变化时，必须重启 Gateway 后再验证。

## 八、测试建议

每次验证新 agent，建议固定做这几步：

1. 先 `/new`
2. 确认 `systemPromptReport` 中注入了预期的 workspace 文件
3. 再问真实问题
4. 查看 session 日志中的 `toolCall`
5. 确认是否走了预期 workflow

重点不要只看最终回答，还要看：

- 是否真的调用工具
- 调用了哪些动作
- 调用顺序是否正确

## 九、不要保留的文件

下面这些通常不应长期留在正式 runtime 目录：

- smoke 数据库
- 一次性 backtest 导出文件
- `__pycache__`
- 临时测试脚本
- 与正式流程无关的中间产物

这些文件应在开发阶段使用，完成后清理。

## 十、推荐交付清单

开发一个新的正式 agent，至少应交付：

- runtime 代码
- 数据库与基础种子数据
- 示例配置
- workspace 根文件模板
- workflow skills
- 中文 README
- 扩展说明
- 基本验证方法

如果缺少其中任意关键项，后续维护成本会明显升高。
