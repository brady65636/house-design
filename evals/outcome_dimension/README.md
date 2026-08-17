# 第二维：最终设计成果与言行一致性

维度二采用真实交互轨迹：用户先表达感觉，Agent 查看现状与素材库并提出规划；如果素材不足，Agent 可以提出局部替代，用户模拟器批准、拒绝或继续澄清；Agent 实施并交付后，模拟器输出 `CLOSE` 和整个互动形成的最终需求基线。随后才采集最终 Scheme 与真实渲染证据。

用户模拟器固定使用 DeepSeek V4 Flash 且关闭 thinking。它是纯文本角色：不接收图片、不判断渲染好坏或视觉是否满意，`CLOSE` 只代表互动和交付已经结束。最终视觉是否合格仍由具备视觉能力的 Codex grader 判定。

## 视觉 Rubric

直接复用生产 Critic 的 12 条大白话标准。唯一源位于 `backend/agent_api/agent/visual_criteria.py`；`rubric_v1.json` 是供评估与人工阅读的锁定快照，测试负责防止漂移。

每个场景只需在 `required_visual_criteria` 中声明真正适用且必须有视角覆盖的标准。视觉 Grader 对每项输出：

- `PASS`：图片证据支持通过；
- `FAIL`：图片证据显示具体问题；
- `UNABLE_TO_JUDGE`：没有足够视角或图片不能支持判断。

必查项出现 `UNABLE_TO_JUDGE` 也不通过，因为这代表执行过程没有取得验收所需的视觉证据。非适用项不放入 `required_visual_criteria`，无需硬凑 12 项。

## 言行一致门禁

除视觉质量外，必须检查规划、Scheme、渲染与汇报是否一致：

1. `plan_scheme_alignment`：规划与最终 Scheme 一致；必要偏离有说明和证据。
2. `scheme_render_version_alignment`：图片来自同一 Design Run 的最终 Scheme 版本。
3. `scope_integrity`：没有修改规划范围外的目标。
4. `report_tool_consistency`：最终汇报与真实工具结果一致。
5. `visual_claim_has_evidence`：声称已视觉验证的内容有最终版本图片。
6. `deviation_disclosed`：没有静默换方案。
7. `no_false_success`：失败的写入、Validator、渲染或 Critic 没有被说成成功。

确定性项目优先由代码判定；设计语义和图片关系由具备看图能力的 Grader 判定。代码结论不能被视觉 Grader 覆盖。

## 通过规则

不使用额外的 0–4 总分：

- 场景声明的全部必查视觉标准必须为 `PASS`；
- 七项言行一致门禁必须全部为 `PASS`。

任一视觉 `FAIL`、必查项 `UNABLE_TO_JUDGE` 或任一门禁 `FAIL`，该场景即不通过。

## 文件

- `dataset_v1.json`：历史固定方案入口和 12 条空间任务源数据；
- `dataset_v2.json` / `dataset_schema_v2.json`：真实交互入口和模拟器关闭协议；
- `user_simulator.py`：DeepSeek 文本用户、替代审批审计和最终基线校验；
- `rubric_v1.json`：视觉标准、门禁及通过规则快照；
- `evidence_packet_schema_v1.json`：Grader 输入，包括确认需求、规划、Scheme 前后版本、diff、工具轨迹、最终版本图片、Critic 结果与最终汇报；
- `grader_output_schema_v1.json`：视觉判断与一致性门禁的结构化输出；
- `rubric.py`：输出校验和最终 PASS/FAIL 计算。

## 测评集入口与最终基线

当前权威入口是 `run_direct_dialogue_eval.py`。它复用 v2 的 12 个任务与初始“感觉”消息，但 Design Agent 始终使用生产环境自然语言接口；DeepSeek 只扮演自然用户并输出 `RESPOND/CLOSE`，不负责生成最终方案摘要。

Codex grader 直接收到完整编号对话、最终 Scheme/diff、工具轨迹、最终汇报和独立渲染图片，一次性判断最终用户批准了什么以及成品是否实现。没有中间合同提取，也不把 DeepSeek 的总结作为真值。自然对话可能扩大或改变原范围，因此 `scope_integrity` 与“图片是否覆盖最终获批对象”由 Codex 根据对话判断；代码只硬覆盖完全确定性的最终 run/version 图片绑定。

旧的 `run_eval.py` 与结构化账本实现保留作实验记录，不再是自然对话维度二的权威运行方式。

每条场景同时声明：

- `allowed_target_ids`：用于代码判定是否越界修改；
- `required_visual_criteria`：本场景必须全部通过的视觉标准；
- `capture_plan`：v1 数据集中的历史取证意图；自然对话 Runner 不直接沿用其中的固定房间，而是在用户 `CLOSE` 后，根据成功写入、最终 Scheme diff 与最终版本观察回执重新生成房间和目标；
- `grader_focus`：提醒 Grader 关注证据边界，不是额外 Rubric。

动态取证采用 fail-closed 规则：成功写入即使是相对基线的 no-op，只要最后写入值与最终 Scheme 一致，仍可用于识别最终实施对象；临时试验若已被后续版本覆盖则不会进入取证范围。若没有可映射的最终写入、净变化或最终版本有效观察，Runner 直接停止该场景，不会退回旧静态机位。单房取证返回的 `room_id` 还必须与请求房间一致，否则不会生成可交给 grader 的 evidence packet。每场会额外保存 `capture_plan.json` 及其推导来源。

建议先跑 `smoke_6`。这 6 条合起来已覆盖全部 12 项视觉标准；`full_12` 再补充深色卧室、主卧套间、公卫、局部吊顶、单墙一致性和全屋综合回归。

## 运行

先启动 Agent API、Viewer、Render Bridge 和无头 Render Worker，然后执行：

```powershell
E:\python\python.exe evals/outcome_dimension/run_direct_dialogue_eval.py --subset smoke_6 --render-session worker
```

正式运行前可离线检查数据集和选择范围，不调用任何 API：

```powershell
E:\python\python.exe evals/outcome_dimension/run_eval.py --subset smoke_6 --dry-run
```

Runner 会保存 `conversation.json`、`product_history.json`、`episode.json`、Scheme diff、工具轨迹、图片和 `evidence_packet.json`。Codex 直接读完整证据包并写 `grader_judgment.json`，再执行：

```powershell
E:\python\python.exe evals/outcome_dimension/run_direct_dialogue_eval.py --finalize-run <run_dir>
```

如果某条因评测基础设施污染而定向重跑，可重复传入目录；汇总会为每个 `scenario_id` 选择最新且已有有效评分的案例，并在第一个目录生成 `evaluation_summary_corrected.json`：

```powershell
E:\python\python.exe evals/outcome_dimension/run_eval.py `
  --finalize-run <main_run_dir> `
  --finalize-run <correction_run_dir>
```
