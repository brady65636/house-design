# 第一维测评集：需求询问与实施前规划

`dataset_v1.json` 用于评估完整设计任务从首条用户需求到实施前规划交付之间的表现。它不评价 Asset 选择、Scheme 成品或真实渲染质量。

## 场景分布

- `sparse`：4 个，需求不足，Agent 应提出少量高价值问题。
- `sufficient`：3 个，需求已经充分，Agent 应停止访谈并直接规划。
- `conflict_or_unknown`：3 个，存在目标冲突或用户无法回答专业术语。
- `boundary`：2 个，包含品牌复刻、报价或结构安全等越界要求。

共 12 个场景：8 个整屋、2 个单房间系统重做、2 个相连公共区任务；其中边界要求嵌入整屋场景。

## 字段解释

- `facts`：模拟用户的稳定事实。`initial` 已在首条消息公开；`if_asked` 仅在 Agent 问题直接相关时披露。
- `must_resolve`：规划前必须通过初始消息或对话获得的信息；不是固定问题清单。
- `must_reflect_in_plan`：规划必须实际吸收的需求关系，不要求固定措辞或唯一设计答案。
- `forbidden`：本场景最重要的错误行为或错误规划方向。
- `max_user_turns`：由测试控制器确定性计数的异常终止上限；当前统一为初始请求之后最多 8 次模拟用户回复，不包含 `CLOSE`。它只防止失控循环，不是理想轮数，也不直接参与评分。

## 终止规则

模拟用户只负责保持人物事实一致，不负责打分：

1. Agent 提问时，根据相关 `if_asked` 事实回答；没有数据时使用全局 `unknown_answer`。
2. Agent 明确交付实施前设计规划且不再等待关键答案时，模拟器输出 `CLOSE`。
3. `CLOSE` 只是测试终止信号，不代表规划合格。
4. 规划完成前成功调用 `update_scheme` 时，控制器立即终止并判硬门禁失败。
5. 达到 `max_user_turns` 仍未交付规划时，控制器以“未形成规划”结束；在上限以内是否提问过多，由“提问质量与效率”软 Rubric 判断。

第一版不设置标准 Asset ID 或唯一参考规划，避免把开放设计问题错误变成答案匹配。

## 运行

先启动正式 Agent API，再从项目根目录执行：

```powershell
# 查看场景
py evals/planning_dimension/run_eval.py --list

# 只校验数据集和选择，不调用模型/API
py evals/planning_dimension/run_eval.py `
  --scenario sparse_whole_home_warm_01 `
  --dry-run

# 跑一个场景
py evals/planning_dimension/run_eval.py `
  --scenario sparse_whole_home_warm_01

# 跑全部场景
py evals/planning_dimension/run_eval.py --all
```

被测 Agent 仍使用它自己的后端配置。模拟用户单独使用 DeepSeek 官方 API：

- `EVAL_AGENT_API_URL`：Agent API，默认 `http://127.0.0.1:8000`；
- `EVAL_AGENT_API_TOKEN`：API Bearer token；未设时回退 `AGENT_API_TOKEN`；
- `EVAL_DEEPSEEK_API_KEY`：DeepSeek API key；未设置时回退 `DEEPSEEK_API_KEY`；
- `EVAL_DEEPSEEK_BASE_URL`：默认且只允许 DeepSeek 官方 `https://api.deepseek.com`；
- `EVAL_DEEPSEEK_PROXY`：可选代理。

模拟器固定使用 `deepseek-v4-flash`，通过项目已有的 OpenAI Python SDK 连接 DeepSeek 官方兼容接口，并在每次 Chat Completions 请求中显式发送 `thinking.type=disabled`。使用 SDK 不等于调用 OpenAI 模型；请求实际发送给 DeepSeek。

每个场景创建独立 `fresh` Design Run。结果按运行时间写入 `results/`，包括完整用户/Agent 对话、模拟器决策、工具调用和版本变化；该目录已被 Git 忽略。

## Grader

运行器不再调用任何 LLM grader。每个场景结束时额外生成一个 `<scenario_id>.grader.json` 最小评分包，只包含 Rubric、场景事实披露状态、编号后的对话、工具调用和代码门禁结果。

需要评分时，由当前 Codex 任务创建独立子 agent，并使用 `fork_turns=none` 把该 JSON 作为唯一评估上下文。子 agent 负责四个非确定性硬门禁和四项 0–4 分软 Rubric；代码负责：

- 根据 fresh Design Run 版本变化判定 `no_premature_update`；
- `max_user_turns` 时强制 `plan_delivered=FAIL`；
- 合并门禁并按“全部门禁 PASS、平均分至少 3、单项不低于 2”计算最终结果。

Codex 子 agent 是当前评估操作的一部分，不是 Python 脚本可以直接调用的公共 API。因此直接在终端运行脚本只负责采集轨迹并生成待评分包；在 Codex 中发起跑测时，再由 Codex 编排子 agent 完成评分。
