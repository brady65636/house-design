# 资产 Family 折叠审计（草案）

> 已废弃：Family 概念于 2026-08-10 取消，资产索引降级为单一 asset 层。本页保留为历史审计基线。

更新时间：2026-08-09

状态：历史审计基线；其 Family 结论已实施。2026-08-09 后续重整进一步把 60 个综合色运行时 ID 合并成 10 个 Asset，明度、饱和度和漆面改由 Scheme 参数表达。当前总目录为 72 Asset / 71 感知 Family，仍保持五品类、55 个稳定设计目标和 34 个墙面 ID。

## 1. 审计结论

当前活动目录共有 114 个可寻址项：墙漆 60、墙纸 15、木地板 12、瓷砖 18、吊顶 9。

墙漆的 60 个项明确折叠为 10 个色彩 Family，每个 Family 由 3 个明度和 2 个漆面展开。其余 54 个项目前各自带有一个 `family` 字段，因此目录名义上共有 64 个 Family。

结合目录 JSON、资产卡和统一目录预览，当前可以确认：

- 60 个 Family 具有较高置信度的独立设计身份；
- 4 个资产形成两组近邻，需要在同一中性房间、同一曝光和同一铺贴尺度下进一步判断；
- 因此当前“人眼可区分 Family”合理区间为 62～64，而不是 114；
- D1 扩充后 Anchor 候选已经不少，当前更突出的缺口是深色 Quiet、连续装饰涂层、精细小模数节奏、收口系统和局部构图能力；
- 最近新增的部分地板、瓷砖和吊顶资产卡仍使用通用说明，`works_well_with` 为空，Agent 尚不能可靠解释它们之间的差异和关系。

这里的 62～64 不是审美评分，而是目录折叠范围。两组待复核项在完成中性房间 A/B 观察前不做永久合并。

## 2. 四层模型

### 2.1 Family

Family 是 Designer 首先选择的材料或构造语言。若两个候选在材料语言、图案语法、空间尺度、表面行为、主要空间角色或搭配逻辑上发生明显变化，应保留为不同 Family。

### 2.2 Variant

Variant 是不改变核心设计语言的受控微调，例如明度、综合色调、漆面、天然变异档位或同系列配色。若参数变化会让资产从 Quiet 变成强 Anchor，并显著改变搭配逻辑，应重新审查它是否仍适合作为普通 Variant。

### 2.3 Configuration

Configuration 描述使用方式，不复制成新材质：

- 地板铺法、方向、板宽和错缝；
- 瓷砖规格、砖缝、排版和起铺点；
- 墙纸比例、对花、旋转、满铺或焦点使用；
- 吊顶模数、方向、下吊高度和灯槽尺寸。

### 2.4 Instance

Instance 是某个 Family、Variant 和 Configuration 在具体 `target_id` 上的实际应用。现有 Scheme v1 可以继续保存确定性解析后的 `asset_id`，避免本轮破坏运行时契约。

## 3. 草案字段

```json
{
  "family_id": "paint_warm_white",
  "category": "wall_paint",
  "coating_system": "solid_paint",
  "design_identity": "克制的近白暖中性纯色涂层",
  "visual_axes": {
    "temperature": "warm",
    "value_range": ["light", "mid", "deep"],
    "pattern_scale": "none",
    "contrast": "low",
    "surface_relief": "micro",
    "surface_response": ["matte", "eggshell"]
  },
  "role_capabilities": {
    "quiet": true,
    "support": true,
    "anchor": "conditional"
  },
  "parameter_dimensions": ["lightness", "saturation", "finish"],
  "configuration_dimensions": ["coverage"],
  "runtime_asset_ids": ["paint_warm_white_01"],
  "relations": {
    "works_with": [],
    "conflicts_with": [],
    "rationale": []
  },
  "audit": {
    "distinctness": "confirmed",
    "evidence": ["catalog", "neutral_room_pending"]
  }
}
```

审美字段采用离散分类和自然语言，不写 `warmth: 0.82` 一类伪精确数值。真实尺寸、粗糙度、重复尺寸、防水和许可仍保留客观数据。

角色代码：`Q` = Quiet，`S` = Support，`A` = Anchor。它表示能力而不是永久身份；最终角色由具体 Scheme 决定。

## 4. 墙漆审计

本节记录重整前的判断依据：当时 60 个运行时 ID 折叠为 10 个 Family，每个 Family 有 `light/mid/deep × matte/eggshell` 六个 Variant。该审计证明这些差异属于可控参数而非独立设计资产；当前实现已变为每个 Family 一个 Asset，并增加连续 `saturation` 参数。

| Family | 运行时项 | 视觉位置 | 角色能力 | 结论 |
| --- | ---: | --- | --- | --- |
| `paint_warm_white` | 6 | 暖、浅到中深、无图案、低对比 | Q/S | 确认；典型全屋基底 |
| `paint_cool_white` | 6 | 冷、浅到中深、无图案、低对比 | Q/S | 确认；当前少数冷静 Quiet 来源 |
| `paint_greige` | 6 | 中性偏暖、浅到中深、低对比 | Q/S | 确认；与木、石材的桥接 Family |
| `paint_taupe` | 6 | 暖中性、中到深、低对比 | Q/S/A | 确认；深色 Variant 可形成包裹感 |
| `paint_charcoal` | 6 | 中性、中到深、低彩度 | S/A | 确认；可作为深色安静背景或焦点 |
| `paint_sage_olive` | 6 | 暖绿、浅到深、低彩度 | S/A | 确认；自然材料桥接 |
| `paint_slate_blue` | 6 | 冷蓝、浅到深、低彩度 | S/A | 确认；冷色沉静方向 |
| `paint_terracotta` | 6 | 暖红棕、浅到深、中等综合色 | S/A | 确认；中色和深色为颜色 Anchor |
| `paint_dusty_rose` | 6 | 灰粉紫、浅到深、低彩度 | S/A | 确认；柔和但成熟的综合色方向 |
| `paint_ochre` | 6 | 暖黄赭、浅到深、中等综合色 | S/A | 确认；与木材使用时需控制泛黄 |

墙漆当前缺口不在综合色相数量，而在所有 Family 共用同一滚筒微表面。项目继续保持现有五品类边界；石灰洗、黏土灰泥、细砂矿物涂层和抛光灰泥仍归入 `wall_paint`，但必须成为新的连续墙面材料 Family，并通过 `coating_system` 区分于 `solid_paint`，不能伪装成普通颜色 Variant。

## 5. 墙纸审计

15 个资产均具有较明确的图案或触觉身份，暂不建议合并。

| Family / Asset ID | 主要设计轴 | 角色能力 | 结论 |
| --- | --- | --- | --- |
| `wallpaper_linen_natural_01` | 暖白、微尺度天然纤维、低对比 | Q/S | 确认 |
| `wallpaper_micro_seed_01` | 暖底、微型满铺节奏、低对比 | Q/S | 确认 |
| `wallpaper_linear_geometry_01` | 暖灰、细竖向秩序、轻压纹 | Q/S | 确认 |
| `wallpaper_soft_arch_geometry_01` | 浅色中尺度现代几何 | S/A | 确认 |
| `wallpaper_botanical_meadow_01` | 浅底自然草本、中尺度有机节奏 | S/A | 确认 |
| `wallpaper_damask_shadow_01` | 低对比古典纹章、选择性压纹 | S/A | 确认 |
| `wallpaper_mineral_wash_01` | 浅色抽象雾染、低到中对比 | S/A | 确认 |
| `wallpaper_mist_landscape_mural_01` | 全景山水叙事壁画 | A | 确认 |
| `wallpaper_ink_branch_01` | 留白、东方墨枝、小到中尺度 | Q/S | 确认 |
| `wallpaper_midcentury_blocks_01` | 暖色高识别几何色块 | A | 确认 |
| `wallpaper_mediterranean_blockprint_01` | 手工木刻植物、中高对比 | S/A | 确认 |
| `wallpaper_art_deco_fan_01` | 深色、高秩序金线几何 | A | 确认 |
| `wallpaper_nocturne_botanical_01` | 冷深色、大尺度植物、沉浸感 | A | 确认 |
| `wallpaper_oxide_colourfield_mural_01` | 非循环综合色域、整墙构图 | A | 确认 |
| `wallpaper_fiber_relief_ripple_01` | 近白雕塑性纤维波纹 | S/A | 确认 |

墙纸已经拥有足够多 Anchor。下一轮只应补明确空白，例如“深色但低对比的素肌理 Quiet”，不再平均增加植物、几何或壁画。

## 6. 木地板审计

| Family / Asset ID | 主要设计轴 | 角色能力 | 结论 |
| --- | --- | --- | --- |
| `floor_ash_maple_light_matte_01` | 浅色、细纹、150mm 板、低变异 | Q | 与漂白白蜡木进入同室 A/B 复核 |
| `floor_light_oak_matte_01` | 浅自然橡木、190mm、适中天然纹理 | Q/S | 确认 |
| `floor_honey_oak_matte_01` | 蜂蜜暖木、中等综合色 | S | 确认 |
| `floor_warm_walnut_matte_01` | 暖红棕、深木、长纹 | S/A | 确认 |
| `floor_smoked_dark_oak_matte_01` | 烟熏灰褐、低明度 | S/A | 确认 |
| `floor_greywashed_variation_matte_01` | 灰洗做旧、高色差 | S/A | 确认 |
| `floor_bleached_ash_wideplank_matte_01` | 漂白浅木、220mm 宽板、低对比 | Q | 与浅白蜡木进入同室 A/B 复核 |
| `floor_caramel_teak_matte_01` | 焦糖橙棕、线性热带木感 | S/A | 确认 |
| `floor_ebonized_oak_matte_01` | 近黑木、低明度、低彩度 | A | 确认 |
| `floor_character_oak_wideplank_matte_01` | 宽板、节疤、高天然变异 | S/A | 确认 |
| `floor_riftsawn_oak_linear_matte_01` | 径切直纹、低变异、线性秩序 | Q/S | 确认 |
| `floor_endgrain_block_matte_01` | 端纹块材、模块化图形 | A | 确认 |

待复核问题：`floor_ash_maple_light_matte_01` 与 `floor_bleached_ash_wideplank_matte_01` 的差异目前主要来自漂白程度和板宽。如果统一铺贴尺度后仍不改变空间角色，应合并为 `floor_pale_ash` Family，颜色和板宽进入 Variant/Configuration。

## 7. 瓷砖审计

| Family / Asset ID | 主要设计轴 | 角色能力 | 结论 |
| --- | --- | --- | --- |
| `tile_plain_mineral_01` | 暖白素色、低对比、规则模数 | Q | 与浅灰微水泥进入同室 A/B 复核 |
| `tile_white_marble_01` | 浅色低对比白石纹大板 | Q/S | 确认 |
| `tile_warm_travertine_01` | 暖米洞石、水平层理 | Q/S | 确认 |
| `tile_dark_slate_01` | 深灰板岩、低反射天然纹理 | S/A | 确认 |
| `tile_light_microcement_01` | 浅灰连续云雾、低对比 | Q | 与暖白素色矿物砖进入同室 A/B 复核 |
| `tile_terrazzo_warm_01` | 暖灰细颗粒水磨石 | Q/S | 确认 |
| `tile_woodlook_oak_01` | 暖木纹长条砖 | S | 确认 |
| `tile_decorative_arc_01` | 中尺度综合色几何花砖 | A | 确认 |
| `tile_terracotta_cotto_01` | 暖橙手工赤陶、窑变 | S/A | 确认 |
| `tile_jade_handglazed_01` | 深绿小规格手工釉 | A | 确认 |
| `tile_blue_white_brush_01` | 蓝白手绘图案、小规格 | A | 确认 |
| `tile_oxblood_small_format_01` | 酒红小规格釉面、低明度 | A | 确认 |
| `tile_checker_black_ivory_01` | 黑白棋盘、高对比几何 | A | 确认 |
| `tile_green_breccia_01` | 深绿角砾石大板、高天然对比 | A | 确认 |
| `tile_ivory_fluted_relief_01` | 象牙竖槽、雕塑性浮雕 | S/A | 确认 |
| `tile_warm_white_zellige_01` | 暖白小规格手工釉、柔和窑变 | Q/S | 确认 |
| `tile_largechip_terrazzo_01` | 大颗粒多色骨料、强图形 | A | 确认 |
| `tile_deep_blue_cloudstone_01` | 深蓝云纹石材大板 | A | 确认 |

待复核问题：`tile_plain_mineral_01` 与 `tile_light_microcement_01` 都承担浅色、低对比、安静矿物背景角色。若统一砖缝和模数后差异不足，应建立 `tile_quiet_mineral` Family，将暖白/浅灰底色和表面云雾作为 Variant；若微水泥的连续感仍显著改变空间效果，则继续分开。

## 8. 吊顶审计

9 个预设在几何语言上均可区分，当前不需要继续加 Family。

| Family / Asset ID | 主要设计轴 | 角色能力 | 结论 |
| --- | --- | --- | --- |
| `ceiling_flat_01` | 平整、最低存在感 | Q | 确认 |
| `ceiling_perimeter_step_01` | 周边跌级、双眼皮秩序 | Q/S | 确认 |
| `ceiling_perimeter_cove_01` | 周边下吊与线性灯槽 | S | 确认 |
| `ceiling_floating_shadow_gap_01` | 悬浮薄板、连续暗缝 | S | 确认 |
| `ceiling_kitchen_bath_panel_01` | 湿区模块化大板 | Q/S | 确认 |
| `ceiling_timber_slatted_01` | 木格栅、强线性节奏 | A | 确认 |
| `ceiling_shallow_coffer_grid_01` | 浅井格、古典网格秩序 | A | 确认 |
| `ceiling_exposed_concrete_shadow_track_01` | 清水混凝土、双轨阴影 | S/A | 确认 |
| `ceiling_curved_cove_01` | 软弧边界、曲面灯槽 | A | 确认 |

吊顶的下一步应是把方向、模数、覆盖区域和灯槽尺度从固定预设中抽为受控 Configuration，而不是继续增加类似预设。

## 9. 角色盘点

从目录预览看，当前强 Anchor 已覆盖：

- 中古综合色几何、地中海木刻、Art Deco 深色几何；
- 深色大植物、全景山水、抽象综合色域壁画；
- 黑白棋盘、青花、酒红釉、深绿角砾石、深蓝云纹石、大颗粒水磨石；
- 乌木化地板、端纹块材、高变异节疤宽板；
- 木格栅、井格、混凝土轨顶和软弧灯槽。

因此 D1 之后不再成立“Anchor 极少”这一判断。新的风险是 Anchor 增长快于 Quiet/Support 关系知识：Agent 很容易把几个有性格的资产同时选中，却缺少足够明确的让位、过渡和收口规则。

## 10. 本轮不做的事情

- 不删除或重命名现有 `asset_id`；
- 不把待复核近邻直接合并；
- 不修改用户已确认的 Scheme v1；
- 不生成 D2 新纹理和 Blender 几何；
- 不把家具重新纳入硬装资产范围；
- 不以单一感知距离、Embedding 或 VLM 分数代替人工设计判断。

下一步依据见 `docs/ASSET_COVERAGE_MATRIX.md` 与 `docs/D2_ASSET_EXPANSION_PROPOSAL.md`。
