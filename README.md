# AI 住宅装修设计 Demo

当前活动场景是 135㎡三居宽厅真实户型 `house_spacious_yunkuo_135_v4`，已接入房间级 Three.js 漫游和完整五品类代表资产库：60 个参数化墙漆、8 个原创墙纸、6 个地板、8 个瓷砖和 5 个吊顶，共 87 个可寻址资产/预设。

![135㎡住宅鸟瞰](output/previews/house_spacious_yunkuo_135_v4.png)

## 当前交付

- Blender 源文件：`output/house_spacious_yunkuo_135_v4.blend`
- Three.js/glTF 文件：`output/house_spacious_yunkuo_135_v4.glb`
- 87 个资产/预设的轻量索引：`output/asset_manifest.json`
- 87 张完整资产卡：`output/asset_cards.json`
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

- `backend/agent_api/`:Agent API(对话 / SSE 流式 / 会话管理 / Scheme 读取),SQLite 持久化会话;
- `backend/render_bridge/`:渲染任务队列(Agent ↔ 浏览器渲染会话);
- `backend/render_worker/`:无头浏览器渲染 worker(playwright + 软件渲染),保证生产环境视觉自评门禁闭环;
- 根目录 `agent_tools.py` / `agent_graph.py` / `render_bridge.py` 等为迁移 shim,兼容旧 CLI 与测试。

本地启动 Agent API:

```bash
python -m uvicorn backend.agent_api.main:app --host 127.0.0.1 --port 8000
```

测试:

```bash
python -m unittest discover -s tests          # 既有 31 项
python -m unittest discover -s backend/tests  # 新增 API/SSE/持久化 10 项
```

前端方案读取已改为 `fetchCurrentScheme()`:优先走 `NEXT_PUBLIC_AGENT_API_URL` 指向的 `/api/scheme`,回退同源 `/current_scheme.json`(本地 dev)。

## 部署上线

前端在 Vercel,后端为常驻容器 PaaS(Docker)。完整步骤、环境变量与 Fly.io / Railway / HuggingFace Spaces 路径见 [docs/DEPLOY.md](docs/DEPLOY.md)。

## 浏览房间级体验

```powershell
cd viewer
npm install
npm run dev -- --host 127.0.0.1
```

打开 `http://localhost:3000/`。页面默认使用客厅人眼高度主镜头；选中墙面后，右侧方案面板可按色彩家族、明度和漆面组合切换全部 60 款墙漆。鸟瞰只作为户型导航，不是主要展示方式。

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

- 87 个资产/预设是否完整装入 v4 源文件，其中包括 14 套地板/瓷砖 PBR 和 5 套吊顶几何；
- 墙漆是否使用完整 PBR 节点、四张 4K 贴图和 60 面色板；
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
