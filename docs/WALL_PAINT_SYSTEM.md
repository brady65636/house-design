# 参数化 PBR 墙漆系统

## 1. 交付范围

第一版墙漆资产不是 60 份重复贴图，而是一套项目原创的参数化 PBR 材质系统：

- 10 个色彩家族；
- 每个家族包含浅色、中色、深色；
- 每个颜色包含哑光、蛋壳光；
- 共 60 个可寻址、可验证的墙漆变体；
- 由同一组 4K 微表面贴图和统一材质参数驱动。

墙漆目录的唯一数据源是 `viewer/app/data/paintCatalog.json`。Blender 生成器、Three.js 运行时、交互面板和测试都消费这份目录，避免颜色、命名和粗糙度在不同模块中漂移。

## 2. 色彩家族

| 家族 | 浅色 | 中色 | 深色 |
|---|---:|---:|---:|
| 暖白与奶油白 | `#F2EADF` | `#DED1C0` | `#BBAA92` |
| 冷白与浅冷灰 | `#F1F2EF` | `#D8DCDA` | `#AEB6B4` |
| 米色与 Greige | `#E5DDD1` | `#C8BEB0` | `#958B7F` |
| 驼色、灰棕与 Taupe | `#D8CCBE` | `#B2A08E` | `#76685D` |
| 中灰与炭灰 | `#D4D3CF` | `#979895` | `#4F5352` |
| 鼠尾草绿与橄榄绿 | `#D9DFD2` | `#A7B29A` | `#66715C` |
| 灰蓝与深蓝 | `#D6DEE1` | `#9AAEB7` | `#536A78` |
| 陶土与锈红 | `#E5C8B7` | `#BD8268` | `#824D3F` |
| 灰粉与藕紫 | `#E4D2D1` | `#B89A9F` | `#745D6A` |
| 黄赭与柔和芥末黄 | `#E7D8B4` | `#C4A66A` | `#806A3E` |

这些是项目原创、经过综合色控制的屏幕预览值，不对应真实品牌 SKU。它们不是实体色卡、光谱测量或施工色差承诺。屏幕、HDR 环境、曝光、底材、光源和施工批次都会改变最终观感。

## 3. PBR 微表面

`viewer/scripts/build-paint-pbr.mjs` 使用固定种子的周期噪声生成可复现、可平铺的 4K 贴图：

- `paint_micro_basecolor_4k.jpg`：接近白色的极轻底色变化，只模拟真实滚涂的不完全均匀；
- `paint_micro_normal_gl_4k.jpg`：细滚筒橘皮和微小施工起伏，强度保持克制；
- `paint_micro_roughness_matte_4k.jpg`：均值约 0.90 的高粗糙度响应；
- `paint_micro_roughness_eggshell_4k.jpg`：均值约 0.66 的柔和反射响应。

物理平铺尺寸为 `0.5m × 0.5m`。微表面只应在近景或掠射光下逐渐显现；如果正常观看距离就出现明显石纹、颗粒斑或重复网格，说明强度或尺度错误。

## 4. 稳定 ID 与兼容

新变体默认使用：

```text
paint_{family}_{tone}_{finish}_01
```

其中 `tone` 为 `light | mid | deep`，`finish` 为 `matte | eggshell`。为兼容既有 Scheme，以下两个 ID 原样保留：

- `paint_warm_cream_matte_01`
- `paint_light_greige_eggshell_01`

结构 GLB 只保留稳定材质名和对象 ID，不重复嵌入 4K 贴图；Three.js 在运行时从统一目录加载共享贴图。Blender 源文件则打包完整 PBR 图像，保证离线材质可复现。

## 5. 生成与验证

生成 PBR 贴图：

```powershell
cd viewer
npm run assets:paint
```

验证目录、亮度顺序、漆面范围和 4K 尺寸：

```powershell
npm run test:paint
```

生成 Blender、GLB、资产清单和完整色板：

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background --factory-startup `
  --python 'blender\generate_house_assets.py'
```

Blender 资产验证会检查 60 个变体、10 个家族、PBR 节点、4K 贴图、60 面色板、稳定墙面 ID 和 GLB 可导入性。

## 6. 视觉验收原则

- 浅、中、深的屏幕相对亮度必须在每个家族中严格递减；
- 哑光和蛋壳光的主要差异来自粗糙度响应，不通过改变颜色伪造；
- 近景可读到微弱滚涂起伏，正常距离保持安静；
- 不允许明显贴图接缝、方向突变、塑料高光和夸张灰泥感；
- 深色墙在 ACES 色调映射下仍保留综合色，不得压成纯黑；
- 同一变体在 Blender 与 Three.js 使用相同 sRGB 色值和同一 PBR 贴图来源。
