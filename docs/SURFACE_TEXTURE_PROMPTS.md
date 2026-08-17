# 地板与瓷砖 ImageGen 提示词记录

生成方式：Codex 内置 ImageGen，2026-08-04。每个不同材质单独生成，输出为 1254×1254 的正方形图像基底，保存到 `output/imagegen/`；`viewer/scripts/build-surface-pbr.mjs` 再进行无缝化、尺度校准，并确定性派生 4K Base Color、OpenGL Normal、Roughness 和 Height。4K 文件是工程派生母版，不声称是原生 4K 扫描。

所有提示词共享约束：正交俯视、均匀漫反射、平面材质扫描；无透视、无场景边缘、无方向性阴影、无镜面高光、无文字、无品牌、无商标、无水印；纹理应能自然重复，但不要生成明显的四方镜像接缝。

## 地板

- `floor_ash_maple_light_generated_v1.png`：浅白蜡木/枫木细纹地板，近白暖米色，细直木纹，色差很低，克制的小导管纹理，哑光清漆，现代安静住宅气质；表现数块约 180mm 宽的长板及细窄板缝。
- `floor_warm_walnut_generated_v1.png`：暖红棕胡桃木地板，中深色，流动的胡桃木纹和少量山形纹，板间色差中等，细微天然结疤，哑光油蜡感；数块约 190mm 宽长板及克制板缝。
- `floor_smoked_dark_generated_v1.png`：烟熏深橡木地板，木炭棕到深咖色，开放橡木导管和少量裂纹，低反光硬蜡油质感，板间色差低到中等；数块约 190mm 宽长板。
- `floor_greywashed_variation_generated_v1.png`：灰洗高色差做旧木地板，冷灰褐、漂白米色和柔和棕灰混合，明显但可信的板间色差，拉丝木纹、轻微风化和少量结疤，哑光；数块约 180mm 宽长板。

## 瓷砖

- `tile_plain_mineral_generated_v1.png`：暖白素色矿物感哑光瓷砖，低对比、细微粉质颗粒和轻柔云雾变化，现代住宅墙地通用；单块 600×600mm 视觉模块，无装饰图案。
- `tile_white_marble_generated_v1.png`：低对比白色大理石纹瓷砖，暖白底，极细且稀疏的浅灰暖灰脉络，避免戏剧性黑纹，柔和缎光石材感；单块 600×1200mm 视觉模块。
- `tile_warm_travertine_generated_v1.png`：暖米色洞石感瓷砖，横向浅层理、细小天然孔洞与柔和奶油/燕麦色差，低对比、哑光磨砂；单块 600×1200mm 视觉模块，不生成模糊条纹。
- `tile_dark_slate_generated_v1.png`：深灰板岩感瓷砖，炭灰到石墨灰，细微片理和矿物变化，低到中等对比，干燥哑光裂面；单块 600×600mm 视觉模块。
- `tile_terrazzo_generated_v1.png`：暖灰细颗粒水磨石，浅暖灰水泥基底，均匀散布米白、灰褐和少量深灰小颗粒，颗粒尺度克制、低对比、细磨哑光；单块 600×600mm 模块。
- `tile_woodlook_generated_v1.png`：暖橡木纹瓷砖，浅蜂蜜橡木色，印刷木纹自然但略比真木均匀，少量导管和结疤，哑光陶瓷表面；单块 200×1200mm 长条模块。
- `tile_decorative_pattern_generated_v1.png`：弧环几何装饰花砖，暖白底，陶土、灰褐与深雾蓝的粗细均衡弧环构成，现代而非复古繁花，图案边缘略带印刷矿物质感，哑光；300×300mm 可四向连续模块。

## 来源说明

`floor_light_oak_matte_01` 与 `floor_honey_oak_matte_01` 的基础木纹继续使用已记录的 Poly Haven `wood_floor` CC0 资产并做色彩派生；`tile_light_microcement_01` 使用固定算法生成的低对比微水泥基底。上述三项没有额外 ImageGen 原图。

## 2026-08-09 多样性扩展第一批

以下八款使用 Codex 内置 ImageGen 单独生成。共同提示要求为：原创材质；正交、顶视或正视、均匀漫反射的平面 Base Color 扫描；无方向光、阴影、镜面高光、反射、透视、景深、场景边缘、文字、品牌、商标或水印。光泽、凹凸和真实受光由确定性 PBR 管线派生。

### 新增地板

- `floor_bleached_ash_wideplank_generated_v1.png`：漂白白蜡木宽板，暖象牙到浅砂色、细直木纹、低色差、极少结疤、干燥哑光；约 220mm 宽长板。避免黄橡木、灰漂流木、厚白漆与做旧裂纹。
- `floor_caramel_teak_generated_v1.png`：焦糖到肉桂棕的柚木，直向流动细纹和少量深色矿物线、低至中色差、哑光油蜡；约 160mm 宽长板。避免橙色亮漆、红木和胡桃木山形纹。
- `floor_ebonized_oak_generated_v1.png`：近黑炭棕乌木化橡木，低对比但可读的开放导管和轻微山形纹、低色差、干燥硬蜡油；约 180mm 宽长板。避免纯黑色块、钢琴亮光和炭烧裂纹。

### 新增瓷砖

- `tile_terracotta_cotto_generated_v1.png`：300×300mm 手工赤陶砖，锈陶、赭石、粉尘桃和土棕窑变，柔和不规则边缘、细矿物点、暖灰砖缝；避免亮橙釉面和破损古砖。
- `tile_jade_handglazed_generated_v1.png`：100×200mm 翠玉手工釉砖，深翠、青瓷绿和苔绿窑变，暖灰细缝；生成图明确禁止镜面高光，釉面响应留给 Roughness/HDR。
- `tile_blue_white_brush_generated_v1.png`：200×200mm 暖白陶砖，以叶片、涟漪、断弧和矿物点组成多款原创钴蓝笔触；避免书法、龙鸟山水、古瓷与 Delft 图案复刻。
- `tile_oxblood_small_format_generated_v1.png`：75×150mm 酒红小规格釉砖，暗酒红、干红、紫棕与深砖红窑变，深暖灰细缝；禁止高光烘焙和鲜红色。
- `tile_checker_black_ivory_generated_v1.png`：ImageGen 生成黑象牙棋盘材质方向样本。视觉复核发现直接无缝化会在黑白边界产生灰色带，因此正式 PBR Base Color 改为项目确定性 `checker_black_ivory` 程序化基底；保留 300×300mm 模数、炭黑/暖象牙矿物变化和暖灰细缝。生成图只作为设计简报记录，不直接进入运行时贴图。

## 2026-08-09 D1 高差异扩展

### 新增地板

- `floor_character_oak_generated_v1.png`：暖中性色宽板橡木，明确保留结疤、矿物线和板间天然差异，用于自然质朴与侘寂方向；避免仿古破损和橙黄亮漆。
- `floor_riftsawn_oak_generated_v1.png`：浅暖径切橡木，连续直纹、极少山形纹和低板间差异，用于安静线性与极简方向。
- `floor_endgrain_block_generated_v1.png`：暖棕端纹木块，以可读年轮端面组成周期模块，不编码成人字或棋盘铺法。

### 新增瓷砖

- `tile_green_breccia_generated_v1.png`：深森林绿角砾石大板，角状碎片、乳白与暖灰细脉，磨砂石材响应。
- `tile_ivory_fluted_relief_generated_v1.png`：象牙竖槽陶瓷的造型参考。生成图带固定方向光，未直接进入正式材质；生产资产由 `ivory_fluted_relief` 程序化 Base Color 与正弦槽形 Height 派生。
- `tile_warm_white_zellige_generated_v1.png`：暖白小规格手工釉砖，轻微奶油/粉灰窑变和不规则边缘，避免强镜面高光。
- `tile_largechip_terrazzo_generated_v1.png`：暖灰基底中的大尺寸彩色矿物骨料，使用窄边周期融合保留骨料轮廓。
- `tile_deep_blue_cloudstone_generated_v1.png`：深靛蓝云纹石材大板，低对比烟雾状矿物带和少量浅灰脉络。

全部正式资产继续由确定性管线生成 Base Color、OpenGL Normal、Roughness、Height、缩略图和接缝指标；`SURFACE_ASSET_IDS` 可用于单个或多个资产的增量重建并安全合并完整清单。

## 2026-08-09 D2 缺口扩展

### 天然细颗粒软木

源文件：`output/imagegen/floor_natural_cork_generated_v1.png`

```text
Use case: stylized-concept
Asset type: project-owned seamless material source for a physically based 3D residential floor
Primary request: create a square, straight-on orthographic diffuse-color source texture of natural fine-grain cork flooring, warm pale tan with restrained honey and soft brown cork cells, calm enough for a large continuous dry-room floor
Style/medium: highly realistic architectural material texture, not a room photograph
Composition/framing: surface fills the entire square edge to edge; even natural granulation; no border; no central feature; no visible plank seams
Lighting/mood: perfectly flat neutral diffuse reference lighting with no directional illumination
Materials/textures: compressed natural cork granules and small irregular cells, fine scale, matte, low-to-medium variation, tactile but quiet
Constraints: seamless/tileable appearance; front-facing orthographic surface; no perspective; no depth-of-field; no cast shadow; no directional shadow; no specular highlight; no gradient; no vignette; no floor edge; no furniture; no text; no logo; no watermark; original generic material with no brand association
Avoid: terrazzo stone chips, OSB wood flakes, bark slabs, large holes, dark burned cork, strong stains, repeated rosettes, photographic lighting
```

### 参数化瓷砖

`tile_cool_finger_mosaic_01`、`tile_smoke_penny_mosaic_01` 和 `tile_deep_matte_monochrome_01` 不使用生成图。正式 Base Color、Height、OpenGL Normal 与 Roughness 由确定性无光照几何规则生成，分别编码 25×100mm 指形模数、50mm 圆点错缝模数和 600×1200mm 深色大砖及真实砖缝。
