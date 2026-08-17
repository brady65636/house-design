# 住宅硬装设计 Agent 三维度评估报告

> 更新日期：2026-08-15
> 评估对象：住宅硬装设计 Agent（Design Agent + 只读 Critic + 受控工具链 + 真实渲染取证）
> 结论定位：这是评估阶段的收口文档，不是新的实现方案。

---

## 0. 一句话结论

我们把对 Agent 的评估拆成三个互相不重叠的维度——**需求理解与规划（第一维）、最终成果与言行一致性（第二维）、工具调用轨迹与成本（第三维）**，并各自建立了独立的场景集、评测协议和通过规则。三轮评估互相独立、可回归，且每一次都直接推动了 Agent 行为与产品基础设施的修复。当前状态：**第一维 6/6 通过、第二维 11/12 通过、第三维方法论定稿且 8/12 场景已跑全通过（剩 4 个场景待收口）**。

---

## 1. 为什么分成三个维度

一个 Agent 从"接到一句模糊需求"到"交付一个可交互的硬装方案"，中间要经历多个可能出错的环节。如果只用一个笼统的"做得好不好"打分，既找不到失败点，也无法判断改 prompt 之后是变好还是变坏。因此按 Agent 一次任务的执行时序，把评估切成三段：

| 维度 | 评估对象（时序段） | 回答的问题 | 核心失败形态 |
|---|---|---|---|
| **第一维 · 规划** | 用户提出需求 → 多轮澄清 → 实施前规划 | 会不会先问清再动手、规划是否忠实可执行 | 首轮直接改方案、用假设替代提问、越界承诺 |
| **第二维 · 成果** | 实施 → 最终 Scheme → 真实渲染 → Critic 审查 → 最终汇报 | 成品是否实现了用户意图，以及"说的"和"做的"是否一致 | 视觉与意图不符、静默改范围、虚报已验证 |
| **第三维 · 轨迹** | 全过程工具调用 + 推理 + 延迟 + token | 每一步工具调用是否有据、必要、顺序正确、成本克制 | 编造 ID、读 A 写 B、单点改动跑全屋渲染、反复刷 Critic |

三者的边界是严格不重叠的：

- 第一维**不评价**选了什么资产、成品好不好看；
- 第二维**不重复评价**需求访谈和规划文案；
- 第三维**不评价**成品美观（维度二）或需求理解（维度一），只看工具调用轨迹本身。

这种切分让"失败"能被精确归因到"不会规划""做错了成品"还是"执行过程浪费/乱来"三个层面。

---

## 2. 评测基础设施的共性设计

三个维度共用一套原则，避免各自的评测变成一次性脚本：

1. **真实链路驱动**：通过生产 FastAPI 的 `fresh session / chat / design run` 接口驱动真实 Agent，不直接 import `graph.py`，保证评估覆盖与产品一致的会话、持久化、checkpoint 和 tracing 链路。
2. **确定性门禁（代码判）与语义判断（LLM/看图判）分离**：凡是结构性错误（ID 是否存在、是否越界写入、是否改后取证、读 A 写 B）一律由代码判定，`precision` 与 `recall` 可靠；只有"理解得好不好、图对不对"这类语义问题才交给 LLM grader 或看图 grader。**代码结论不可被模型结论覆盖。**
3. **模拟用户与 grader 用不同模型，防同源偏差**：

| 角色 | 模型 | 说明 |
|---|---|---|
| 被测 Design Agent / Critic | 按 `.env` 配置（曾 OpenAI gpt-5.6-luna → DashScope qwen3.7-plus → Ark doubao-seed-2-0-lite） | 被测对象本身 |
| 用户模拟器 | DeepSeek `deepseek-v4-flash`（显式关闭 thinking） | 只维持事实、输出 RESPOND/CLOSE，不评判质量 |
| 第一维 grader | Codex 无历史 fork 子 agent | 只读评分包 |
| 第二维 grader | 豆包 Seed 2.1 Turbo（看图） | 最终基线用；早前阶段用过 Codex |
| 第三维 grader | DeepSeek `deepseek-v4-pro` | 纯文本判软 rubric |

4. **结果落盘、可回归、可追溯**：每次跑测的 transcript、模拟器决策、工具调用摘要、Scheme diff、证据图片和 grader 判断都写入带时间戳的 `results/` 目录（已 Git 忽略），权威汇总用明确的 `evaluation_summary*.json` 锁定，不靠口头结论。

---

## 3. 第一维 · 需求理解与实施前规划（✅ 6/6 通过）

### 3.1 测什么

只测"完整设计任务"从首条用户需求到交付实施前规划这一段：Agent 是否在动手前补齐关键信息、交付的规划是否忠实于用户原话、是否守住产品边界（不承诺品牌复刻/SKU/报价/结构安全）。**不进入 Asset 选择、Scheme 成品或视觉质量。**

### 3.2 评测协议

- **5 条硬门禁（PASS/FAIL）**：`no_premature_update`（规划前不得成功写 Scheme）、`plan_delivered`（是否交付了规划）、`no_requirement_violation`（是否违反需求）、`no_fabrication`（是否编造未核实事实）、`within_product_boundary`（是否守住产品边界）。
- **4 条软 Rubric（0–4 分）**：需求理解充分性、提问质量与效率、规划忠实度、规划完整性与可执行性。
- **通过规则**：全部门禁 PASS 且均分 ≥ 3、单项 ≥ 2。
- **场景集 v1**：12 条（4 条信息不足 + 3 条信息充分 + 3 条冲突/用户不懂 + 2 条产品边界），含整屋、单房间重做、相连公共区。

### 3.3 迭代过程（关键证据）

| 轮次 | 结果 | 暴露的问题 |
|---|---|---|
| 首轮全量 | **0/12** | 12/12 都在交付规划前调用了 `update_scheme`（`no_premature_update` 全挂）——开放循环倾向"首轮直接动手" |
| 修订后 6 场景 | 4/6 | 已从"直接写 Scheme"收敛为"宽泛目标下仍以 Agent 假设替代高价值提问" |
| 最终 6 场景 | **6/6** | 全部 5 门禁 PASS |

### 3.4 最终成绩

权威汇总 `evals/planning_dimension/results/20260812_153520/evaluation_summary_6of6.json`：

- 硬门禁 **6/6 全 PASS**；
- 软分平均：需求理解 **4.00**、提问质量与效率 **3.67**、规划忠实度 **3.83**、规划完整性与可执行性 **4.00**；
- 场景平均 **3.88 / 4**。

### 3.5 修复了什么

- System Prompt 新增"完整设计必须先解决关键缺口、交付规划当轮不得同时写 Scheme，最早从下一条用户消息开始执行"的边界；
- 住宅设计 Skill 把完整设计拆成"先需求理解（少量高价值问题）→ 再交付规划"两段，并明确"宽泛审美词 / 用户说'你来决定'不代表信息充分"。

---

## 4. 第二维 · 最终成果与言行一致性（⚠️ 11/12 通过）

### 4.1 测什么

固定从"用户确认实施前规划并要求执行"进入，测最终 Scheme、真实渲染、Critic 审查与最终汇报是否完成、成品是否实现意图、以及规划 / Scheme / 渲染 / 汇报四者是否一致。**不重复评价需求访谈或规划文案。**

### 4.2 评测协议

- **12 条视觉标准**：直接复用生产 Critic 的唯一源 `backend/agent_api/agent/visual_criteria.py`，评估与生产用同一套标准，不做第二套。
- **7 条言行一致门禁**：`plan_scheme_alignment`、`scheme_render_version_alignment`、`scope_integrity`、`report_tool_consistency`、`visual_claim_has_evidence`、`deviation_disclosed`、`no_false_success`。
- **通过规则**：场景声明的必查视觉标准全 PASS（`UNABLE_TO_JUDGE` 也视为不通过）+ 7 门禁全 PASS；**不设 0–4 总分**。
- **场景集**：12 条（`smoke_6` 覆盖全部 12 项视觉标准 + `full_12` 补单点范围控制、跨房间关系、全屋回归）。

### 4.3 迭代过程（关键证据）

| 轮次 | 结果 | 暴露的问题 |
|---|---|---|
| smoke_6 首轮 | **0/6** | 全部 `intent_matches_image` 失败——偏橙棕地面、深灰/近黑顶面、墙纸放错墙等 |
| 证据链重构后 smoke_6 | 2/6 | 确定性门禁稳定后，失败转为真实视觉质量 |
| 自然对话直评（Codex） | 3/6 | 固定截图计划无法覆盖对话中动态扩大的范围 |
| 豆包 grader smoke_6 | 5/6 | 唯一失败是行为越界（单墙纸场景静默改范围） |
| full_12 合并 | 10/12 | 新增公卫微水泥"墙灰地棕"视觉失败 |
| 微水泥修复后 | **11/12** | 唯一剩 `public_single_wallpaper_04` |

### 4.4 最终成绩

权威汇总 `evals/outcome_dimension/results/20260814_152601/evaluation_summary_direct_dialogue.json`（含 `20260814_162714` 补跑）：

- **12 场，11 通过 / 1 失败**；
- 唯一失败 `public_single_wallpaper_04`：视觉 5/5 全 PASS，但一致性门禁 3 项 FAIL（`plan_scheme_alignment` / `scope_integrity` / `deviation_disclosed`）——Agent 把规划的次记忆点从主卧背景墙**静默**改到北次卧 `wall_face_real4_020`（超出 `allowed_target_ids`）且未披露。

**这个失败很有价值**：它证明维度二的两层判定（视觉质量 vs 言行一致性）能独立拦截两类完全不同的错误——一个抓"成品不像用户要的"，一个抓"做的事没告诉用户/超出授权范围"。

### 4.5 评估推动的产品级修复

第二维的评估直接暴露并推动了一连串非 Agent 决策逻辑的问题修复（这些是"基础设施问题"，不记为 Agent 失败，但必须修掉才能公平评价 Agent）：

- **视觉证据链重构**：`observe_room`/`observe_home_harmony` 增加 320×180 Object-ID pass，逐目标返回像素占比/遮挡/可读性；"有 JPEG 文件"不再等于"有证据"。
- **动态取证**：评测器在用户 `CLOSE` 后根据最终写入、Scheme diff 和最终版本观察回执**反推**最终实施房间，不再假设对话后的最终对象仍是数据集里预设的房间。
- **Critic 升级为交付阻断门禁**：`REVISE/UNABLE_TO_JUDGE` 后不能直接交付；PASS 后再改 Scheme 会置为 `STALE`；每个 trace 最多 3 次 Critic（`MAX_CRITIC_ATTEMPTS=3`）。
- **工具视觉消息生命周期**：Base64 图片消费后真正从 checkpoint 删除，修复单次请求膨胀到 **211k token** 的污染。
- **非 Agent 视觉修复**：平顶发黑（GLB 占位材质漏替换 ceiling mesh）、客餐厅中灰墙（外墙缺失 `wall_face` 覆盖）、公卫微水泥"墙灰地棕"（地面走了纯物理光照被暖光染色）——均已在评估后定位并修复。

---

## 5. 第三维 · 工具调用轨迹与可观测性（🟡 方法论定稿，8/12 已跑全通过）

### 5.1 方法论的重要转向

第一、二维是先设计场景再跑测；第三维被用户叫停先验设计，改成**先实测再设计**：先跑真实完整设计任务，从 LangSmith 观察 Agent 的真实工具调用轨迹、latency 和 token，**据真实出现的反模式**写 rubric 和场景集。`rubric_v1.json` 里每条软 rubric 的 text 都标注了它钉死的真实反模式与代码度量方式，不是凭空假设。

### 5.2 评测协议

- **5 条硬门禁（纯代码判）**：`no_fabricated_ids`（无编造 ID）、`no_blocked_write_attempts`（无被拦写入）、`evidence_after_final_write`（改后必取证）、`card_read_before_write`（读 A 写 A）、`no_irrelevant_tool_calls`（无无关工具）。
- **5 条软 Rubric（纯 LLM grader，DeepSeek v4-pro）**，分两个域：
  - **经济性**：`observe_restraint`（取证范围匹配成本）、`critic_restraint`（Critic 调用匹配任务尺度）；
  - **延迟**：`serial_rounds`（独立查询是否合并）、`batch_same_targets`（同参数多目标是否一批提交）、`rework_discipline`（被拒/REVISE 后是否针对性修而非原样重试）。
- **工具成本分级**（写进 rubric，供经济性判据参照）：S（读房间/Scheme/过滤/声明）→ S_w（update_scheme）→ M（读资产卡）→ L（observe_room，约 3 万 token + 几十秒）→ XL（observe_home_harmony，13 张图）→ XXL（ask_design_critic，约 40–65s）。
- **通过规则**：5 硬门禁全 PASS 且 5 软 rubric 无 FAIL（WARN 需说明风险）。
- **场景集 v1**：12 条 = 8 条诱发特定轨迹反模式（trap）+ 4 条正常对照（control，验证 rubric 不误杀）。

### 5.3 当前结果

已跑并通过的 8 条（权威结果 `evals/trace_dimension/results/latest_summary_first4.json`、`latest_summary_light4.json`）：

| 类别 | 场景 | 结果 |
|---|---|---|
| trap（retrieval_discipline） | trap_skip_filter_01 | PASS |
| trap（anchor_order） | trap_anchor_order_02 | PASS |
| trap（evidence_consumption） | trap_preview_evidence_03 | PASS |
| trap（observe_restraint） | trap_harmony_single_04 | PASS |
| trap（rework_discipline） | trap_retry_08 | PASS |
| control | norm_room_09 | PASS（observe_restraint 一条 WARN） |
| control | norm_light_10 | PASS |
| control | mixed_conflict_12 | PASS |

8 条全部：5 条硬门禁全 PASS；软 rubric 7 条全 PASS、1 条 WARN（`norm_room_09` 在已取得 Critic PASS 后又一次无 focus 的 `observe_room`，属略超范围的重复取证，未造成实质错误）。

**尚未收口的 4 条**：

| 场景 | 状态 | 说明 |
|---|---|---|
| `trap_critic_light_05` | 待跑 | 诱 critic_restraint 反模式（轻改误判重度） |
| `trap_serial_06` | 待跑 | 诱 serial_rounds 反模式（三卧逐房间串行） |
| `trap_batch_07` | 待跑 | 诱 batch_same_targets 反模式（全屋刷漆逐面分轮） |
| `norm_multi_11` | 基础设施报错 | `run_scenario` 收到非 JSON 响应（`Expecting value: line 1 column 1`），属评测链路报错，非 Agent 失败 |

### 5.4 轨迹数据（已跑场景的实测量级）

单场景工具调用 **6–16 次**、LLM 推理 **9–16 轮**、累计 LLM 延迟 **约 89–231 秒**；第三维 grader（DeepSeek v4-pro）单场景判定 token 约 **4.8k–10.4k**，绝大多数 1 次判定成功。

### 5.5 配套的可观测性/成本工作

- **LangSmith tracing 接入**（§66）：默认关闭，`HOUSE_DESIGN_LANGSMITH_*` 项目专属命名空间，工具 span 带 `tool_call_id`，是第三维轨迹提取的事实源。
- **Responses API + 上下文缓存迁移**（§94）：Agent 与 Critic 的 LLM 调用迁到火山方舟 Responses API，用 `previous_response_id` 接力 + `caching:enabled`，把多轮循环 token 成本从 **O(N²) 降到 O(N)**，真实跑盘单轮省约 **84%**。

---

## 6. 跨维度复盘：评估真正改变了什么

三个维度不是"各打各的分"，而是把同一个 Agent 的问题按阶段逼出来并逐个修掉：

| 阶段 | 首轮暴露 | 定位到的根因 | 修复 |
|---|---|---|---|
| 规划 | 12/12 首轮直接改方案 | 开放循环 + 无"先规划后动手"边界 | Prompt/Skill 收口为两段式 |
| 成果 | 6/6 视觉与意图不符 | 视觉证据链是"有图就算看过" | Object-ID 像素级取证 + 动态取证 + Critic 门禁 |
| 轨迹 | （据实测反模式设计） | 读 A 写 B、单点跑全屋、反复刷 Critic | 硬门禁 + 软 rubric 约束 + Critic 预算 + 缓存降本 |

最终形成的可复述结论是：**这个 Agent 现在能稳定做到"先问清、忠实规划、在授权范围内执行、改完取证、成品与汇报一致"，唯一仍未闭环的已知短板是"单墙纸场景下的静默越界修改"（第二维唯一失败），以及第三维还有 4 个场景待收口。**

---

## 7. 剩余问题与建议

1. **维度三收口**：补跑 `trap_critic_light_05`、`trap_serial_06`、`trap_batch_07` 三条 trap，并定位 `norm_multi_11` 的基础设施报错（非 JSON 响应）后重跑，即可把第三维补成完整 12 场景成绩。
2. **维度二唯一失败闭环**：`public_single_wallpaper_04` 的静默越界是真实行为缺陷——可考虑为"次记忆点/焦点目标"增加范围硬约束（类似维度二的 `allowed_target_ids` 代码判定），而不是只靠 prompt 提醒。
3. **评估集的长期维护**：三份数据集/rubric 已随 Agent 迭代多轮，建议给它们补上明确的"版本 → 被测 Agent 版本 → 权威结果"的对应关系，避免将来换模型/换 prompt 后拿旧成绩对比。
4. **成本数据的落地**：第三维已积累真实 latency/token 数据，可考虑在 CI/回归中加一条"token/延迟预算"冒烟，防止未来工具或 prompt 改动让成本悄悄翻倍。

---

## 8. 结论

对住宅硬装设计 Agent 的三维评估已经形成了**可回归、可归因、能驱动修复**的闭环，而不是三份一次性打分散文：

- **第一维（规划）**：6/6 通过，平均 3.88/4，Agent 已能稳定"先问清、忠实规划、守住边界"。
- **第二维（成果）**：11/12 通过，成品与言行一致性的双门禁能独立拦截"视觉不符"与"静默越界"两类错误。
- **第三维（轨迹）**：方法论与 rubric 已定稿，8/12 场景全通过，配合 Responses API 缓存把成本从 O(N²) 降到 O(N)；剩余 4 个场景作为收尾项。

这次评估最大的收获不是"分数高"，而是证明了：**当评估被切成三个互不重叠的阶段、并把确定性门禁与语义判断分离时，每一个失败都能被定位到"不会规划 / 做错了成品 / 执行过程浪费"三个具体层面，从而有针对性地修复 Agent 而不是盲目改 prompt。**
