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
