# 参数化 PBR 墙漆系统

## 1. 交付范围

墙漆品类是两层项目原创 PBR 材质系统：10 个参数化综合色 Asset，以及 3 个具有独立纹理集的连续矿物涂层 Asset。

- 10 个色彩家族，每个家族只对应一个稳定 `asset_id`；
- `lightness` 在 `light | mid | deep` 三个校准锚点之间选择；
- `saturation` 是 `0.35–1.25` 的连续数值参数，默认 `1.0`；
- `finish` 在 `matte | eggshell` 之间选择；
- 共 13 个可寻址、可验证的墙面涂层 Asset：10 个综合色 Asset，石灰洗、黏土灰泥、Marmorino 各 1 个；
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

## 4. Asset 与参数契约

综合色墙漆使用不包含明度、饱和度或漆面的稳定 ID：

```text
paint_{slug}_01
```

Scheme 在具体墙面实例上保存参数：

```json
{
  "target_id": "wall_face_001",
  "asset_id": "paint_greige_01",
  "parameters": {
    "lightness": "light",
    "saturation": 0.85,
    "finish": "matte"
  }
}
```

旧的 `paint_{slug}_{tone}_{finish}_01` 仅作为迁移输入识别，不再出现在运行时 Asset 索引中。迁移脚本为 `scripts/migrate_paint_asset_parameters.py`。

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

Blender 资产验证会检查 13 个墙漆 Asset、参数 Schema、PBR 节点、4K 贴图、综合色板与矿物涂层板、稳定墙面 ID 和 GLB 可导入性。

## 6. 视觉验收原则

- 浅、中、深的屏幕相对亮度必须在每个家族中严格递减；
- 哑光和蛋壳光的主要差异来自粗糙度响应，不通过改变颜色伪造；
- 近景可读到微弱滚涂起伏，正常距离保持安静；
- 不允许明显贴图接缝、方向突变、塑料高光和夸张灰泥感；
- 深色墙在 ACES 色调映射下仍保留综合色，不得压成纯黑；
- 同一 Asset 与同一组参数在 Blender 与 Three.js 使用相同 sRGB 色值和同一 PBR 贴图来源。
