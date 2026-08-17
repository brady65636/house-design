# 资产卡多模态图片契约

每张资产卡必须包含一个 `preview_image`：

```json
{
  "path": "viewer/public/assets/asset-cards/paint_greige_01_preview.webp",
  "media_type": "image/webp",
  "depiction": "parameter_swatch",
  "alt": "米色与 Greige 墙漆的浅、中、深参数色阶预览；屏幕色不替代实体色卡。"
}
```

`depiction` 只允许表达图片是什么，不是审美分数：

- `parameter_swatch`：参数化墙漆的浅、中、深色阶；
- `material_thumbnail`：墙纸、地板、瓷砖或固定矿物涂层的材质目录图；
- `geometry_preview`：吊顶几何目录图，不是施工节点图。

`get_asset_card_by_id` 会在同一次工具结果中返回卡片 JSON 与图片 data URL。Graph 随后把图片作为模型的 `image_url` 内容块注入。图片路径必须位于项目目录内，格式限 WebP/JPEG/PNG，单图不超过 4MB；缺图、越界路径和不支持格式均显式失败。

资产预览只回答“候选本身长什么样”。它不能证明资产应用到当前房间后的比例、光照、过渡和竞争关系；这些结论仍必须来自 `observe_room` / `observe_home_harmony`。因此资产卡图片不会写入最终渲染回执，也不能绕过 final-only Critic 门禁。

运行 `npm run assets:cards` 可从现有目录缩略图、墙漆参数色阶和 Blender 吊顶目录图确定性重建全部 72 张统一预览。
