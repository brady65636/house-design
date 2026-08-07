# 原创墙纸 PBR 系统

## 1. 完成范围

第一版墙纸库已完成 8 个原创系列。`viewer/app/data/wallpaperCatalog.json` 是 Blender、Three.js、生成脚本、交互面板和测试共用的唯一目录数据源。

| 顺序 | Asset ID | 系列 | 物理重复 / 成品尺寸 | 对花 | 推荐方式 |
|---|---|---|---|---|---|
| 01 | `wallpaper_linen_natural_01` | 天然亚麻 | 0.53 × 0.53m | 随机拼 | 满铺 / 焦点墙 |
| 02 | `wallpaper_micro_seed_01` | 矿物籽点 | 0.265 × 0.265m | 直拼 | 满铺 / 焦点墙 |
| 03 | `wallpaper_linear_geometry_01` | 暖灰织纹线 | 0.53 × 0.32m | 直拼 | 满铺 / 焦点墙 |
| 04 | `wallpaper_soft_arch_geometry_01` | 柔拱构成 | 0.53 × 0.64m | 错位对花 | 焦点墙 |
| 05 | `wallpaper_botanical_meadow_01` | 雾野草本 | 0.53 × 0.64m | 错位对花 | 焦点墙 / 克制满铺 |
| 06 | `wallpaper_damask_shadow_01` | 影纹章 | 0.53 × 0.64m | 直拼 | 焦点墙 |
| 07 | `wallpaper_mineral_wash_01` | 矿物雾染 | 1.06 × 1.06m | 错位对花 | 焦点墙 |
| 08 | `wallpaper_mist_landscape_mural_01` | 雾境层峦壁画 | 4.40 × 2.80m | 五幅连续壁画 | 焦点墙 |

`match_type` 记录未来实物卷材的施工对花规则。实时 3D 使用的是完成铺贴后的连续表面表达，不把卷材裁切边或施工缝烘进基础色贴图；它不是印刷滚筒排版文件或施工放样图。

## 2. 为什么不能直接“颜色转法线”

旧管线把基础色亮暗直接转换为法线，结果会把植物墨线、抽象色块和壁画山体误当成实体凹凸。新管线将表面拆为三层：

1. 基础色只负责图案、色彩与印刷变化；
2. 高频与周期噪声负责毫米级纸纤维、织纹和细小施工表面；
3. 只有线性、现代几何与 Damask 等明确压纹类型，才允许受控的中尺度高度参与 Normal 和 Height。

因此，植物和壁画的印刷内容在掠射光下仍保持平面；Damask 的压纹小于毫米，只在近景和斜光下读取。

## 3. 资产分层

### 原创源图

- 位置：`output/imagegen/`
- 生成方式：Codex 内置 ImageGen，逐款调用、逐款检查；Damask 首稿因块状感过强返修一次。
- 完整提示词：`docs/WALLPAPER_TEXTURE_PROMPTS.md`

### 4K PBR 母版

- 位置：`output/wallpapers_pbr/`
- 每款包含 Base Color、OpenGL Normal、Roughness、Height；共 32 张贴图。
- 循环款最长边 4096px，并按物理宽高输出矩形贴图，避免非方形重复尺寸造成像素拉伸。
- 壁画另保留 `8192 × 5216` 的生产母版：`output/imagegen/wallpaper_mist_landscape_mural_01_master_8k.jpg`。

### Three.js 运行时

- 位置：`viewer/public/assets/wallpapers/`
- 循环款使用 2K 基础色与优化后的 2K WebP 线性贴图；壁画基础色保留 4K。
- 缩略图与 PBR 分开，面板只加载轻量缩略图。
- 除默认亚麻外，其余墙纸点击时才加载 PBR，避免一次下载全部高精度纹理。

## 4. 真实尺度与 UV

30 面编号墙的 UV 已改为米制：U 表示墙面水平方向的米数，V 表示高度米数。材质重复由：

```text
repeat_u = 1 / pattern_width_m
repeat_v = 1 / pattern_height_m
```

计算，不再根据某一面 4.40 × 2.80m 墙硬编码重复次数。因此同一资产应用到不同墙宽时仍保持真实比例，壁画也不会因为立方体默认 UV 被旋转或拉伸。

实时客厅的西侧标杆墙实测宽 4.51m，比 4.40m 壁画成品宽 110mm。Three.js 预览对壁画 U/V 各增加很小的安全拟合余量（4.52 × 2.82m），避免斜视角下 `ClampToEdge` 将单行边缘像素放大成拖影；生产母版、五幅分幅与施工元数据仍严格保持 4.40 × 2.80m。该余量只属于实时展示适配，不应回写到印刷尺寸。

## 5. 可复现构建

```powershell
cd viewer
npm run assets:wallpaper
npm run test:wallpaper
```

重新生成 Blender、GLB 与验证报告：

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python blender/generate_house_assets.py
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background output/house_2b2l_90_v1.blend --python blender/validate_outputs.py
```

## 6. 验收

- 8 个稳定 Asset ID、8 个视觉系列、8 套来源记录；
- 七款循环基础色四边平均像素误差为 0；
- 32 张 PBR 母版的尺寸、存在性与 Blender 节点自动检查；
- 8 个 Blender 墙纸材质都包含 Base Color、Normal、Roughness、Height；
- 客厅西墙 UV 范围为约 `0–4.51m × 0–2.80m`；
- Blender/GLB 独立验证 27 项全部通过；
- Three.js 正式构建、目录测试和运行时逐款切换必须通过。

## 7. 边界

- 这些资产是项目原创代表设计，不是品牌 SKU，也不能替代实物色样、印刷打样和施工对花确认。
- ImageGen 源图经过确定性无缝化，但“像素无缝”不等于在所有距离都没有视觉重复；`output/previews/wallpaper_repeat_check.png` 用于人工检查重复节奏。
- 壁画 8K 文件是高质量重采样生产母版，不应被描述为原生 8K 模型输出。
