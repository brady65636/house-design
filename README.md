# AI 住宅装修设计 Demo

当前活动场景是 135㎡三居宽厅真实户型 `house_spacious_yunkuo_135_v4`，已接入房间级 Three.js 漫游和完整五品类代表资产库：13 个墙漆/连续涂层、16 个原创墙纸、13 个地板、21 个瓷砖和 9 个吊顶，共 72 个可寻址的自描述 Asset。10 个综合色墙漆各自只保留一个 Asset，明度、饱和度和漆面均作为 Scheme 参数。

![135㎡住宅鸟瞰](output/previews/house_spacious_yunkuo_135_v4.png)

## 当前交付

- Blender 源文件：`output/house_spacious_yunkuo_135_v4.blend`
- Three.js/glTF 文件：`output/house_spacious_yunkuo_135_v4.glb`
- 72 个自描述资产/预设的轻量索引：`output/asset_manifest.json`
- 72 张完整资产卡：`output/asset_cards.json`
- 房间与表面清单：`output/scene_manifest.json`
- 自动验证报告：`output/validation_report_spacious_v4.json`
- 建模规格：`docs/MODEL_SPEC.md`
- 可复现生成脚本：`blender/generate_spacious_floorplan_v4.py`
- 独立验证脚本：`blender/validate_spacious_floorplan_v4.py`
- Three.js 房间体验：`viewer/app/components/RoomExperience.tsx`
- 相机与室内参照数据：`viewer/app/components/interiorScene.ts`
- 客厅真实感标杆间：`viewer/app/components/heroLivingScene.ts`
- 原创现代沙发生成器：`blender/generate_hero_sofa.py`
- 客厅摄影级渲染器：`blender/render_hero_living.py`
- 外部资产许可记录：`docs/ASSET_LICENSES.md`
- 墙漆系统说明：`docs/WALL_PAINT_SYSTEM.md`
- 完整墙漆色板：`output/previews/paint_catalog.png`

五类产品资产均为项目原创或明确记录来源的代表资产，不对应真实品牌 SKU；客厅中的部分中性家具与环境素材使用 Poly Haven CC0 资产。当前住宅用于产品和技术验证，不是施工图，也不声称满足结构、消防或当地住宅规范。

## 后端(Agent API)

Agent 后端已从 CLI 拆分为 FastAPI 服务,代码收拢在 `backend/` 包:

- `backend/agent_api/`:Agent API(对话 / SSE 流式 / 会话管理 / Design Run 与 Scheme 版本),SQLite 持久化会话、JSON 持久化隔离设计运行;
- `backend/render_bridge/`:渲染任务队列(Agent ↔ 浏览器渲染会话);
- `backend/render_worker/`:无头浏览器渲染 worker(playwright + 软件渲染),保证生产环境视觉自评门禁闭环;
- 旧 CLI 迁移 shim(agentloop / agent_tools / agent_graph / render_bridge 等)与配套旧测试已归档至 `exp/legacy-cli/`;新代码一律从 `backend.agent_api.*` 导入。

本地启动 Agent API:

```bash
python -m uvicorn backend.agent_api.main:app --host 127.0.0.1 --port 8000
```

本地 `.env` 的模型配置使用项目专属变量；系统级 `OPENAI_*`、`DASHSCOPE_*`、`ARK_*`、
`DEEPSEEK_*` 不会被后端读取。当前默认 provider 为火山方舟 Ark（豆包多模态模型，
支持视觉与工具调用）：

```dotenv
HOUSE_DESIGN_LLM_PROVIDER=ark
HOUSE_DESIGN_ARK_API_KEY=ark-...
HOUSE_DESIGN_ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
HOUSE_DESIGN_ARK_MODEL=doubao-seed-2-0-lite-260428
HOUSE_DESIGN_REASONING_EFFORT=none
```

需要切回阿里云百炼时，把 `HOUSE_DESIGN_LLM_PROVIDER` 改为 `dashscope` 并配置
`HOUSE_DESIGN_DASHSCOPE_API_KEY` / `HOUSE_DESIGN_DASHSCOPE_BASE_URL` /
`HOUSE_DESIGN_DASHSCOPE_MODEL`；切回 OpenAI 时改为 `openai` 并配置
`HOUSE_DESIGN_OPENAI_API_KEY` / `HOUSE_DESIGN_OPENAI_BASE_URL` /
`HOUSE_DESIGN_OPENAI_MODEL`（可选 `HOUSE_DESIGN_OPENAI_PROXY`）。

三个 provider 都会在启动阶段校验官方 API 地址：OpenAI 只允许
`https://api.openai.com/v1`，DashScope 只允许
`https://dashscope.aliyuncs.com/compatible-mode/v1`，Ark 只允许
`https://ark.cn-beijing.volces.com/api/v3`，阻止把凭据发送到
DeepSeek、兼容网关或其他接口。修改 `.env` 后必须重启后端进程。

可选的 LangSmith 追踪同样使用项目专属变量，默认关闭，也不会读取系统级
`LANGSMITH_*` / `LANGCHAIN_*`。启用后，每轮 LangGraph、模型调用、手写工具分发、
渲染观察和嵌套 Critic 会写入同一个 trace：

```dotenv
HOUSE_DESIGN_LANGSMITH_TRACING=true
HOUSE_DESIGN_LANGSMITH_API_KEY=lsv2_...
HOUSE_DESIGN_LANGSMITH_ENDPOINT=https://api.smith.langchain.com
HOUSE_DESIGN_LANGSMITH_PROJECT=house-design-agent
# 只有 API key 关联多个 workspace 时才填写：
HOUSE_DESIGN_LANGSMITH_WORKSPACE_ID=
```

Trace 会携带 `thread_id`、`design_run_id`、`design_mode`、传输方式和模型名等非密钥
元数据。关闭 tracing 时，即使系统环境误设了通用 LangSmith 变量，本项目也不会上传。
启用 tracing 表示对话、工具参数/结果，以及进入模型上下文的实时渲染证据会发送到所配置的
LangSmith workspace；不要在未经授权的真实住宅或敏感用户数据上直接开启。

测试:

```bash
python -m unittest discover -s backend/tests
```

前端方案读取已改为 `fetchCurrentScheme()`:优先走 `NEXT_PUBLIC_AGENT_API_URL` 指向的 `/api/scheme`,回退同源 `/current_scheme.json`(本地 dev)。

对话页 `/chat`(主页右上角「对话助手」进入)通过 `viewer/app/chat-proxy/[...path]/route.ts` 服务端代理调用聊天/会话接口——token 由 house-viewer 进程注入,不进浏览器 bundle;SSE 流式回复 + 工具调用实时展示。新对话默认创建隔离的“从零设计”运行，也可选择复制当前为分支或继续当前方案；详细生命周期与恢复规则见 [`docs/DESIGN_VERSIONING.md`](docs/DESIGN_VERSIONING.md)。

## 部署上线

前端在 Vercel,后端为常驻容器 PaaS(Docker)。完整步骤、环境变量与 Fly.io / Railway / HuggingFace Spaces 路径见 [docs/DEPLOY.md](docs/DEPLOY.md)。

## 浏览房间级体验

```powershell
cd viewer
npm install
npm run dev -- --host 127.0.0.1
```

打开 `http://localhost:3000/`。页面默认使用客厅人眼高度主镜头；选中墙面后，右侧方案面板先选择 10 个综合色墙漆 Asset 之一，再用明度、饱和度和漆面参数调整实例；也可选择 3 个独立矿物连续涂层。鸟瞰只作为户型导航，不是主要展示方式。

客厅已经作为第一间真实感标杆空间升级：使用 PBR 木地板、灰泥墙和织物微表面，HDR 环境反射、软阴影、GTAO 接触阴影，以及真实休闲椅/茶几和项目原创现代沙发。页面右上角可切换 Blender Cycles 摄影级静帧与实时 Three.js；其他房间仍保留较轻量的空间参照，暂不应被描述为同等完成度。

## 重新生成

本机已安装 Blender 5.2.0 LTS。PowerShell 中执行：

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background `
  --factory-startup `
  --python 'blender\generate_spacious_floorplan_v4.py'
```

脚本会覆盖 `output` 中同名的生成物，但不会修改源规格或项目记忆。

## 验证

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background 'output\house_spacious_yunkuo_135_v4.blend' `
  --python 'blender\validate_spacious_floorplan_v4.py'
```

验证内容包括：

- 72 个资产/预设是否完整装入 v4 源文件，其中包括 34 套地板/瓷砖 PBR 和 9 套吊顶几何；
- 综合色墙漆是否使用共享完整 PBR 节点，三种矿物涂层是否使用独立 4K PBR；
- 135㎡场景的 11 个空间、55 个设计目标和 34 个墙面 ID 是否完整；
- 模型是否使用米制尺寸、应用变换并处于预期边界；
- GLB 是否能重新导入；
- `surface_id` 和 `asset_id` 是否通过 glTF extras 保留；
- 四张预览图的尺寸是否正确。

## 这一步训练的能力

这批资产主要覆盖项目学习阶梯中的 Level 2 和 Level 4 基础：

- 把住宅、房间、表面和资产区分成稳定的数据概念；
- 理解材质资产与几何构造预设的区别；
- 使用自定义属性把 Blender 对象连接到未来的 Scheme JSON；
- 理解 Blender 的 Z-up 坐标与 glTF/Three.js 导出边界；
- 用独立验证程序证明输出可靠，而不是只看渲染图。

Three.js 已经完成 v4 GLB 加载、房间级摄影机和 Scheme 材质切换闭环，并接入完整五品类目录。下一步应补齐资产卡 Schema、风格说明书和 Agent 访谈流程，而不是继续增加未结构化的代表资产。

## 废弃内容归档 exp/

`exp/` 存放不再参与当前 v4 管线的废弃内容,已在 `.gitignore` 中忽略(不进入版本控制,但保留在磁盘便于追溯):

- `exp/legacy-cli/`:旧 CLI 迁移 shim、`agentloop`、一次性资产知识生成器与配套旧测试;
- `exp/blender-v1-v3/`:v1/v2/v3 户型的生成/验证脚本及一次性数据迁移脚本;
- `exp/output-archive/`:旧场景(v1/v2/v3)的 .blend/.glb、旧 scene_manifest / validation_report、户型研究参考图与历史日志;
- `exp/viewer-template/`:viewer 的 Cloudflare/vinext 模板残留(worker/build/.openai/db/drizzle/examples)与旧前端模型/方案/图标;
- `exp/caches/`:`__pycache__`、`.pytest_cache` 等可再生缓存。

需要找回某项时从对应子目录移回即可。完整说明见 `exp/README.md`。
