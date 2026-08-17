# 135㎡ v4 住宅与完整表面资产规格

## 1. 活动住宅

- ID：`house_spacious_yunkuo_135_v4`
- 类型：三室两厅两卫，含玄关、主卧衣帽间、玻璃移门厨房和 7.6m 南向开放阳台
- 标称建筑面积：135.0 m²；公开套内参考：96.53 m²
- 概念模型矩形空间面积：103.70 m²；阳台：14.44 m²
- 外轮廓：13.4 m × 9.8 m
- 墙体高度：3.1 m
- 坐标：米制，Z 轴向上，西南外角为 `(0, 0, 0)`

v4 是当前唯一活动住宅。模型追求可用于 Agent/Three.js 闭环的稳定空间与表面 ID；公开面积用于比例校准，概念矩形面积不替代测绘、施工图、结构、消防或当地住宅规范。

## 2. 房间、地面/顶面与墙面编号

| 房间 | 房间 ID | 地面表面 ID | 顶面表面 ID | 独立墙面数 |
|---|---|---|---|---:|
| 完整横厅客厅 | `open_public` | `surface_real4_floor_open_public` | `surface_real4_ceiling_open_public` | 6 |
| 南次卧 | `bedroom_3` | `surface_real4_floor_bedroom_3` | `surface_real4_ceiling_bedroom_3` | 4 |
| 玄关 | `foyer` | `surface_real4_floor_foyer` | `surface_real4_ceiling_foyer` | 2 |
| 餐厅 | `dining_room` | `surface_real4_floor_dining_room` | `surface_real4_ceiling_dining_room` | 2 |
| 玻璃移门厨房 | `kitchen` | `surface_real4_floor_kitchen` | `surface_real4_ceiling_kitchen` | 4 |
| 公卫 | `guest_bath` | `surface_real4_floor_guest_bath` | `surface_real4_ceiling_guest_bath` | 3 |
| 北次卧 | `bedroom_2` | `surface_real4_floor_bedroom_2` | `surface_real4_ceiling_bedroom_2` | 4 |
| 主卧 | `master_bedroom` | `surface_real4_floor_master_bedroom` | `surface_real4_ceiling_master_bedroom` | 3 |
| 主卧衣帽间 | `master_dressing` | `surface_real4_floor_master_dressing` | `surface_real4_ceiling_master_dressing` | 4 |
| 主卫 | `master_bath` | `surface_real4_floor_master_bath` | `surface_real4_ceiling_master_bath` | 2 |
| 7.6m 南向开放阳台 | `south_panorama_balcony` | `surface_real4_floor_south_panorama_balcony` | — | 0 |

墙面不再预先合并成 `surface`。每个房间侧墙面使用稳定的 `wall_face_id`，Agent 直接建立：

```text
wall_face_id -> asset_id
```

同一物理墙的两侧拥有不同编号，但通过 `host_wall_id` 保留共享构件关系。门窗洞口周围即使由多个网格片组成，也共享同一个 `wall_face_id`。

v4 共提供 34 个稳定 `wall_face_id`、11 个地面和 10 个顶面，合计 55 个 Scheme 设计目标。完整的人类可读代码、中文名称、房间、朝向、物理墙、默认 Asset、兼容类别、几何范围和洞口引用写入活动 `scene_manifest.json`。地面和顶面使用 `surface_id`；吊顶结构预设使用 `preset_id`。

## 3. 首批代表资产与完整扩展

### 墙漆

1. `paint_warm_white_01`：暖白色彩 Asset；明度、饱和度、漆面由 Scheme 参数决定。
2. `paint_greige_01`：Greige 色彩 Asset；明度、饱和度、漆面由 Scheme 参数决定。

### 墙纸

1. `wallpaper_linen_natural_01`：低对比天然亚麻织物肌理。
2. `wallpaper_micro_seed_01`：暖底矿物蓝灰微型籽点满铺。
3. `wallpaper_linear_geometry_01`：细尺度暖灰织纹线性秩序。
4. `wallpaper_soft_arch_geometry_01`：低对比陶土灰柔拱现代几何。
5. `wallpaper_botanical_meadow_01`：橄榄灰与赭色雾野草本。
6. `wallpaper_damask_shadow_01`：当代低对比解构 Damask。
7. `wallpaper_mineral_wash_01`：烟蓝、陶土与橄榄灰矿物雾染。
8. `wallpaper_mist_landscape_mural_01`：4.40 × 2.80m 非循环雾境层峦壁画。

### 地板

完整目录为 6 套：浅白蜡木细纹、浅色自然橡木、蜂蜜色暖木、暖红棕胡桃、烟熏深橡木、灰洗高色差做旧木。物理板宽、铺法、重复尺寸和 PBR 参数见 `viewer/app/data/floorCatalog.json`。

### 瓷砖

完整目录为 8 套：暖白素色矿物、低对比白色大理石纹、暖米洞石、深灰板岩、浅灰微水泥、暖灰细颗粒水磨石、暖橡木纹砖、弧环几何装饰花砖。物理模数、缝宽、铺法和 PBR 参数见 `viewer/app/data/tileCatalog.json`。

### 吊顶

完整目录为 9 套：原顶或平顶、周边跌级双眼皮、周边下吊灯槽、悬浮顶与阴影缝、厨卫模块化大板、木格栅、浅井格、清水混凝土双阴影轨道和弧形灯槽。下降高度、周边带宽、灯槽/暗缝尺寸、格栅/梁网参数和干湿区适用性见 `viewer/app/data/ceilingCatalog.json`。

这些都是项目原创的代表性资产，不对应或冒充任何真实品牌 SKU。

### 墙漆完整扩展（2026-08-02）

墙漆品类包含 10 个综合色 Asset，以及石灰洗、黏土灰泥、Marmorino 三个独立连续涂层 Asset，共 13 个可寻址项。综合色的 `lightness`、`saturation`、`finish` 均由 Scheme 参数表达，不再生成独立 Asset ID；旧 Variant ID 仅供迁移脚本识别。完整色值、物理参数、生成方法和验收要求见 `docs/WALL_PAINT_SYSTEM.md`。

### 墙纸完整扩展（2026-08-02）

墙纸已扩展为 16 个原创系列。每款记录物理重复尺寸、对花方式、使用位置、微表面类型和来源许可；Blender 使用 4K Base Color / Normal / Roughness / Height，Three.js 使用优化运行时贴图并按需加载。完整目录、生成方法和验收要求见 `docs/WALLPAPER_SYSTEM.md`。

## 4. 交付与验收

- `house_spacious_yunkuo_135_v4.blend` 能在 Blender 中继续编辑，且内含完整 v4 资产目录集合。
- `house_spacious_yunkuo_135_v4.glb` 能被标准 glTF 查看器或 Three.js 加载。
- `.blend` 内包含全部 72 个资产的数据块或几何预设：13 个墙漆/连续涂层、16 个墙纸、13 个地板、21 个瓷砖和 9 个吊顶。
- 34 个房间侧墙面拥有稳定且不重复的 `wall_face_id`，并保留 `room_id`、`host_wall_id`、`wall_code` 和 `asset_id`。
- 地面/顶面继续拥有稳定的 `surface_id`，吊顶结构继续拥有 `preset_id`。
- 所有物体使用真实米制尺寸，无负缩放，导出前应用变换。
- 提供住宅鸟瞰图和资产目录预览图。
- 提供 JSON 清单，供后续 Scheme 验证器和前端读取。
