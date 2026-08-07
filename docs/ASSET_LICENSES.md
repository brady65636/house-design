# 视觉资产来源与许可

客厅标杆间使用了项目原创资产和 Poly Haven 的 CC0 资产。Poly Haven 的资产许可说明：<https://polyhaven.com/license>。

## 项目原创

- `viewer/public/assets/hero-living/hero_modern_sofa.glb`
  - 生成脚本：`blender/generate_hero_sofa.py`
  - 来源：程序化原创
  - 许可：项目自有
- 客厅地毯、窗帘、装饰画、柜体、灯具和小型陈设
  - 生成实现：`viewer/app/components/heroLivingScene.ts`
  - 来源：程序化原创
  - 许可：项目自有
- 8 个原创墙纸系列及其 PBR 纹理
  - 图像基底：OpenAI 内置 ImageGen 逐款生成；要求平视扫描、无品牌、无文字、原创图案，并逐张人工检查。Damask 首稿未采用，最终稿经过一次定向返修
  - 完整源文件和提示词：`output/imagegen/`、`docs/WALLPAPER_TEXTURE_PROMPTS.md`
  - 单一数据目录：`viewer/app/data/wallpaperCatalog.json`
  - PBR 派生脚本：`viewer/scripts/build-wallpaper-pbr.mjs`
  - 4K PBR 母版：`output/wallpapers_pbr/`；Three.js 优化运行时：`viewer/public/assets/wallpapers/`
  - 许可：项目自有，不对应真实品牌或 SKU
- 参数化 PBR 墙漆系统
  - 色彩目录：`viewer/app/data/paintCatalog.json`
  - PBR 生成脚本：`viewer/scripts/build-paint-pbr.mjs`
  - 最终资产：`viewer/public/assets/paints/`
  - 来源：固定种子周期噪声程序化生成，包含 4K Base Color、Normal 和两种 Roughness
  - 许可：项目自有；60 个变体均为屏幕预览色，不对应真实品牌、SKU 或实体色卡
- 6 套地板与 8 套瓷砖 PBR 系统
  - ImageGen 原图：`output/imagegen/`
  - 完整提示词：`docs/SURFACE_TEXTURE_PROMPTS.md`
  - 目录：`viewer/app/data/floorCatalog.json`、`viewer/app/data/tileCatalog.json`
  - PBR 派生脚本：`viewer/scripts/build-surface-pbr.mjs`
  - 4K 派生母版：`output/surfaces_pbr/`；Three.js 运行时贴图：`viewer/public/assets/surfaces/`
  - 来源：11 张无品牌 ImageGen 材质基底、既有 Poly Haven `wood_floor` CC0 原图，以及一套固定算法生成的微水泥基底；所有结果统一做无缝化并确定性派生 Normal、Roughness、Height
  - 许可：ImageGen 与程序化部分为项目自有；Poly Haven 部分沿用 CC0；均不对应真实品牌或 SKU
- 5 套吊顶几何预设
  - 目录：`viewer/app/data/ceilingCatalog.json`
  - Blender 几何：`blender/generate_spacious_floorplan_v4.py` 内的 `V4_ASSET_LIBRARY`
  - Three.js 房间适配几何：`viewer/app/components/RoomExperience.tsx`
  - 来源：项目原创参数化几何
  - 许可：项目自有；仅作概念设计和屏幕预览，不是施工节点

## Poly Haven CC0

- `wood_floor`
  - 页面：<https://polyhaven.com/a/wood_floor>
  - 用途：客厅木地板 Base Color、Normal、Roughness
- `white_plaster_02`
  - 页面：<https://polyhaven.com/a/white_plaster_02>
  - 用途：早期客厅灰泥墙研究资产，文件保留作材质对照；当前正式墙漆运行时已改用项目原创 PBR 系统
- `fabric_pattern_05`
  - 页面：<https://polyhaven.com/a/fabric_pattern_05>
  - 用途：软包和窗帘的织物 Normal、Roughness
- `cayley_interior`
  - 页面：<https://polyhaven.com/a/cayley_interior>
  - 用途：室内环境反射与环境光
- `modern_arm_chair_01`
  - 页面：<https://polyhaven.com/a/modern_arm_chair_01>
  - 用途：客厅休闲椅
- `modern_coffee_table_01`
  - 页面：<https://polyhaven.com/a/modern_coffee_table_01>
  - 用途：客厅茶几

这些外部资产仅作为中性空间参照，不对应首版五类产品库中的可采购 SKU。
