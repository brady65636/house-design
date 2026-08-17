# Asset 保守否决过滤器

## 它解决的问题

72 个自描述 Asset 全部交给 Design Agent 会浪费上下文和渲染轮次。本模块只排除明显不适合的选择，并把每一类候选压缩至少 70%；它不判断哪个方案最美。

执行链路：

```text
完整 Asset 列表
  -> target / room 硬兼容检查
  -> ANCHOR / SUPPORT / QUIET 明显冲突否决
  -> 分层多样性候选预算
  -> Design Agent 实际应用、渲染、比较
```

## 为什么第一版不用 LAB + 单一复杂度分数

平均 LAB 会把多色图案压成一个均值；只从 Base Color 计算复杂度会漏掉 Normal/Height 浮雕、大尺度低对比图案和深色图案。第一版只保留人工校准的离散区间，不建立加权总分，也不允许一个优点抵消明确硬冲突。

过滤档案位于 `asset_filter_profiles.json`。`activity` 必须综合 Base Color、Normal/Height、图案尺度和真实目录预览人工校准；它不是自动图像指标，也不是美学分数。

## 输入契约

- `target_id`：活动住宅中的真实设计目标。
- `category`：五类资产之一，且必须在目标允许类别中。
- `role`：`anchor | support | quiet`。
- `anchor_asset_id`：已有视觉锚点；设计锚点本身时可为空。
- `color_intent`：`open | harmonious | contrasting`；只有 `harmonious` 会启用极端冷暖高彩冲突否决。

## 输出契约

- `eligible`：送给 Design Agent 做真实渲染比较的候选。
- `rejected`：确定性硬冲突或高置信关系冲突。
- `deferred`：本身不坏，只因 70% 候选预算暂缓。
- `metrics`：输入/输出数量、硬否决数、预算暂缓数、缩减率和是否达标。

稳定原因码：

- `ROOM_MOISTURE_INCOMPATIBLE`
- `ROOM_TYPE_INCOMPATIBLE`
- `CONTINUOUS_PATTERN_ON_FRAGMENTED_TARGET`
- `HIGH_ACTIVITY_FOR_QUIET_ROLE`
- `DUAL_HIGH_ACTIVITY`
- `EXTREME_HARMONIOUS_COLOR_CONFLICT`
- `DIVERSITY_BUDGET`

警告不会否决候选：

- `MEDIUM_ACTIVITY_FOR_QUIET_ROLE`
- `STRONG_DIRECTION_COMPETITION`
- `DUAL_DARK_VALUE`

## 失败方式与验收

最大风险是误删仍然可用的方案。为此，只有高置信冲突进入 `rejected`，数量预算造成的移除单独进入 `deferred`；Design Agent 必须保留最终视觉判断权。

第一版验收：

- 当前五类资产查询的候选缩减率均不低于 70%；
- 每个硬拒绝都有稳定原因码；
- 高活动 ANCHOR 不再配入高活动 SUPPORT；
- QUIET 不保留高活动候选；
- 连续壁画不进入有门窗切割的墙面候选；
- 过滤器不写 Scheme、没有副作用。
