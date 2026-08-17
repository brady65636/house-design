# 墙纸原创图案生成记录

生成方式：Codex 内置 ImageGen。每个不同资产单独调用；结果保存到 `output/imagegen/`，再由 `viewer/scripts/build-wallpaper-pbr.mjs` 确定性无缝化并派生 PBR。所有提示词均禁止文字、品牌、商标和水印。

## 01 天然亚麻

源文件：`output/imagegen/wallpaper-linen-generated-v1.png`

```text
Use case: photorealistic-natural
Asset type: seamless PBR base-color texture for a real-time Three.js interior wallcovering
Primary request: Create a truly seamless square albedo texture of premium natural linen wallpaper, photographed/scanned perfectly flat and orthographic. The surface should be warm off-white flax with very fine irregular warp-and-weft fibers, subtle thread thickness variation, occasional tiny slubs, extremely restrained tonal variation, and a high-end matte wallcovering character. It must read as an almost calm solid color from several meters away and reveal convincing fibers only up close.
Lighting: perfectly even diffuse scan lighting; no directional light, shadows, highlights, vignette, or depth-of-field.
Composition: texture fills the entire square edge to edge; seamless/tileable on all four edges; no border.
Constraints: physically plausible fine-scale fibers; no obvious repeat; no large woven checkerboard; no panel seams; no folds; no draped fabric; no wall scene; no objects; no text; no logo; no watermark.
Avoid: coarse grid, basket weave, stripes, moire, stains, decorative motifs, perspective, edge discontinuities.
```

## 02 矿物籽点

源文件：`output/imagegen/wallpaper-micro-seed-generated-v1.png`

```text
Use case: photorealistic-natural
Asset type: original seamless base-color texture for a premium residential wallpaper PBR material
Primary request: Create an original, truly seamless square repeat of a refined micro seed-dot wallpaper. The design uses tiny offset seed-shaped marks and pin dots arranged in a quiet, precise all-over rhythm, sophisticated and architectural rather than cute or illustrative.
Scene/backdrop: the wallpaper surface fills the entire canvas edge to edge.
Style/medium: flat orthographic high-resolution material scan, premium non-woven matte wallcovering, not a room photograph.
Composition/framing: perfectly front-facing square tile; repeat must connect continuously on all four edges; no border, no center focal point, no large motif.
Lighting/mood: perfectly even diffuse scan lighting; no directional light, shadows, highlights, vignette, glare, depth of field, or perspective.
Color palette: warm parchment base, very low-contrast mineral blue-gray and soft charcoal micro marks; restrained overall contrast.
Materials/textures: extremely subtle cellulose fibers and fine paper grain visible only up close; printed marks remain visually flat, not thick paint.
Constraints: original design from scratch; realistic tiny residential wallpaper scale; calm from several meters away; dense but breathable rhythm; seamless on all four edges; no text, no letters, no numbers, no logos, no trademarks, no watermark.
Avoid: polka dots, childish motifs, flowers, stars, obvious grid, coarse fabric weave, moire, stains, folds, panel seams, wall scene, objects, strong color variation, edge discontinuities.
```

## 03 暖灰织纹线

源文件：`output/imagegen/wallpaper-linear-generated-v1.png`

```text
Use case: photorealistic-natural
Asset type: seamless PBR base-color texture for a real-time Three.js interior wallcovering
Primary request: Create a truly seamless square albedo texture of premium fine linear geometric wallpaper, photographed/scanned perfectly flat and orthographic. Use a warm greige natural-fiber paper base with very subtle narrow vertical pinstripes and micro-embossed linear rhythm. The lines should have restrained irregularity and tiny fiber detail, with a sophisticated architectural character. From several meters away it should read as a calm warm greige surface; the linear pattern becomes legible only at medium and close distance.
Lighting: perfectly even diffuse scan lighting; no directional light, shadows, highlights, vignette, or depth-of-field.
Composition: texture fills the entire square edge to edge; seamless/tileable on all four edges; no border.
Constraints: physically plausible paper fibers; fine low-contrast linear pattern; no obvious repeat; no panel seams; no folds; no wall scene; no objects; no text; no logo; no watermark.
Avoid: broad decorative stripes, high contrast bands, coarse checkerboard, moire, fabric drape, stains, perspective, edge discontinuities.
```

## 04 柔拱构成

源文件：`output/imagegen/wallpaper-soft-arch-generated-v1.png`

```text
Use case: photorealistic-natural
Asset type: original seamless base-color texture for a premium residential wallpaper PBR material
Primary request: Create an original, truly seamless modern geometric wallpaper built from softly broken arches, offset semicircles, and thin architectural line segments. The repeat should feel ordered but not rigid, with generous negative space and a quiet contemporary rhythm suitable for a refined living-room focal wall.
Scene/backdrop: wallpaper surface fills the entire canvas edge to edge.
Style/medium: flat orthographic high-resolution material scan of premium matte non-woven wallpaper; original geometric print, not a room photograph.
Composition/framing: perfectly front-facing square repeat tile; balanced all-over layout; pattern connects continuously on all four edges; no border and no single center motif.
Lighting/mood: perfectly even diffuse scan lighting, no directional shadows, highlights, glare, vignette, perspective, or depth of field.
Color palette: warm pale stone background, thin muted clay lines, restrained charcoal-gray secondary lines, occasional soft greige fill; low-to-medium contrast.
Materials/textures: very subtle paper fibers; selected line segments may have barely perceptible shallow embossing, but the design must remain physically plausible wallcovering.
Constraints: original design from scratch; elegant real-world wallpaper scale; seamless on all four edges; strong at medium distance but calm in the full room; no text, letters, numbers, logos, trademarks, or watermark.
Avoid: Bauhaus replicas, recognizable designer patterns, Memphis style, loud primary colors, thick black outlines, optical illusion, 3D blocks, perfect corporate icon grids, moire, folds, panel seams, wall scene, objects, edge discontinuities.
```

## 05 雾野草本

源文件：`output/imagegen/wallpaper-botanical-meadow-generated-v1.png`

```text
Use case: photorealistic-natural
Asset type: original seamless base-color texture for a premium residential wallpaper PBR material
Primary request: Create an original, truly seamless botanical wallpaper composed from airy meadow herbs, slender seed heads, small asymmetric leaves, and a few abstract unopened buds. The plants should interweave lightly in a natural half-drop rhythm without forming bouquets or a central scene.
Scene/backdrop: wallpaper surface fills the canvas edge to edge.
Style/medium: refined hand-drawn botanical ink and dry-brush print translated into a flat orthographic high-resolution material scan on matte non-woven paper; not a room photograph.
Composition/framing: perfectly front-facing square repeat tile; graceful upward botanical movement; balanced negative space; continuous repeat on all four edges; no border and no center focal point.
Lighting/mood: perfectly even diffuse scan lighting; no shadows, highlights, vignette, glare, depth of field, or perspective.
Color palette: warm parchment and limestone base; muted olive-gray foliage, soft charcoal stems, extremely restrained dusty ochre accents; calm natural contrast.
Materials/textures: subtle cellulose paper grain and faint dry-print irregularity; ink remains flat; no painted impasto.
Constraints: original plant forms designed from scratch; sophisticated residential scale; seamless on all four edges; visually calm at room distance and detailed at close range; no animals, birds, insects, text, letters, logos, trademarks, or watermark.
Avoid: recognizable species illustration plates, tropical monstera or palm leaves, roses, peonies, chinoiserie scenes, William Morris imitation, vintage fabric look, bouquets, symmetrical vines, photographic flowers, wall scene, folds, panel seams, edge discontinuities.
```

## 06 影纹章

最终源文件：`output/imagegen/wallpaper-damask-shadow-generated-v1.png`

首稿结构提示词：

```text
Use case: photorealistic-natural
Asset type: original seamless base-color texture for a premium residential wallpaper PBR material
Primary request: Create an original contemporary damask wallpaper with a large, vertically ordered medallion rhythm. Build each medallion from abstract acanthus-like curls, softened shield contours, and fragmented mirrored flourishes, deliberately deconstructed so it evokes classical ornament without copying any historic textile or existing wallpaper.
Scene/backdrop: wallpaper surface fills the canvas edge to edge.
Style/medium: flat orthographic high-resolution material scan on premium matte fibrous non-woven paper; subtle tone-on-tone screen print with shallow embossed ornament; not a room photograph.
Composition/framing: perfectly front-facing square repeat tile; restrained bilateral structure; repeat connects continuously on all four edges; no border; no single emblem isolated in the center.
Lighting/mood: perfectly even diffuse scan lighting; no directional shadow, highlight, glare, vignette, perspective, or depth of field.
Color palette: warm limestone and mushroom-taupe, shadowy gray-brown ornament, a trace of muted mineral charcoal; low contrast with no metallic gold.
Materials/textures: fine natural paper grain; ornament may be gently embossed by less than a millimeter, readable mainly in grazing light.
Constraints: original design from scratch; sophisticated contemporary-classical residential scale; seamless on all four edges; calm enough for a focal wall; no crowns, coats of arms, monograms, heraldic animals, text, letters, logos, trademarks, or watermark.
Avoid: direct Victorian, Baroque, Rococo, French toile, hotel-brocade, palace-gold, fabric sheen, recognizable archival damask, tiny busy lace, photographic depth, folds, panel seams, room scene, edge discontinuities.
```

首稿因块状模板感过强未采用；最终使用一次单变量编辑：

```text
Use case: precise-object-edit
Asset type: refined original seamless wallpaper base-color texture
Primary request: Refine only the ornamental drawing in the previous damask image: replace the blocky stencil-like fragments with thinner, more graceful, softly tapered deconstructed acanthus curves and quieter layered tone-on-tone shapes. Make the medallion structure feel premium, delicate, and contemporary rather than craft-cut or heavy.
Constraints: preserve the same warm limestone and mushroom-taupe palette, low contrast, flat orthographic scan, overall medallion spacing, paper grain, bilateral rhythm, edge-to-edge coverage, and absence of a room scene. Keep the pattern original and seamless. No metallic gold, no text, no logos, no trademarks, no watermark.
Avoid: blocky cut-paper shapes, thick stencils, sharp heraldic emblems, dense lace, recognizable historic damask, glossy fabric, perspective, shadows, folds, or panel seams.
```

## 07 矿物雾染

源文件：`output/imagegen/wallpaper-mineral-wash-generated-v1.png`

```text
Use case: photorealistic-natural
Asset type: original seamless large-repeat base-color texture for a premium residential wallpaper PBR material
Primary request: Create an original abstract mineral-wash wallpaper with broad translucent brush veils, softly feathered dry edges, mist-like ink diffusion, and restrained overlapping fields. The composition should feel atmospheric and hand-made while avoiding any recognizable object or landscape.
Scene/backdrop: wallpaper surface fills the entire canvas edge to edge.
Style/medium: flat orthographic high-resolution material scan; layered mineral pigment and diluted ink printed on matte fibrous non-woven paper; not a room photograph or framed artwork.
Composition/framing: perfectly front-facing square large-repeat tile; broad movements pass through the borders so all four edges can connect; balanced all-over flow with no central focal point and no visible panel.
Lighting/mood: perfectly even diffuse scan lighting; no shadows, directional highlights, glare, vignette, perspective, or depth of field.
Color palette: warm chalk and pale stone base, smoke blue-gray, muted terracotta haze, trace olive-gray, soft charcoal dilution; low-to-medium chroma and restrained contrast.
Materials/textures: fine cellulose paper grain; translucent pigment variation and dry-print speckling remain visually flat.
Constraints: original abstract composition from scratch; sophisticated large residential scale; seamless on all four edges; calm in a full room but richly layered up close; no text, calligraphy, letters, symbols, logos, trademarks, or watermark.
Avoid: obvious mountains, clouds, horizon, faces, objects, dramatic black ink, alcohol-ink clichés, marbling, tie-dye, watercolor paper buckling, framed-art composition, folds, panel seams, room scene, edge discontinuities.
```

## 08 雾境层峦壁画

源文件：`output/imagegen/wallpaper-mist-landscape-mural-generated-v1.png`

```text
Use case: stylized-concept
Asset type: original full-wall panoramic residential mural master artwork for a 4.40 m wide by 2.80 m high feature wall
Primary request: Create an original atmospheric landscape mural of layered imaginary ridgelines emerging through pale mist. The landscape should be abstracted and timeless: broad mineral silhouettes, soft eroded edges, quiet valleys, and a distant luminous opening, with no identifiable real place, building, person, animal, or cultural monument.
Scene/backdrop: the artwork itself fills the entire canvas; no room mockup, wall edges, furniture, floor, or ceiling.
Style/medium: refined mineral-pigment wash, dry-brush haze, and translucent ink layers printed on matte fibrous wallcovering; original contemporary mural, not a photograph and not imitation of any named artist or historical painting.
Composition/framing: wide panoramic 11:7 aspect ratio matching a 4.40 x 2.80 m wall; primary visual weight below the horizontal center; open pale mist through the upper third; layered depth from soft foreground at the bottom to faint distant ridges; important forms stay away from the extreme left and right edges so vertical installation panels do not cut a focal subject.
Lighting/mood: diffuse dawn-like luminosity inside the painted atmosphere, quiet, contemplative, spacious, no directional photographic sun or cast shadows.
Color palette: warm chalk, pale limestone, smoke blue-gray, muted olive-gray, restrained taupe, and a trace of dusty terracotta; low chroma and controlled contrast.
Materials/textures: subtle cellulose paper grain and mineral speckling visible up close, no glossy paint or thick impasto.
Constraints: original artwork from scratch; designed as one non-repeating full-wall mural; high-detail panoramic composition; no text, calligraphy, seals, letters, logos, trademarks, or watermark.
Avoid: recognizable Chinese shanshui copying, Japanese screen-painting imitation, famous landscape composition, photorealistic mountains, sharp alpine peaks, dramatic sunset, fantasy castle, birds, trees as focal icons, people, buildings, horizon banding, symmetrical center, frame, border, panel seams, room scene.
```

壁画生产母版：`output/imagegen/wallpaper_mist_landscape_mural_01_master_8k.jpg`。这是高质量重采样的 `8192 × 5216` 母版，不宣称为模型原生 8K 输出。

## PBR 输出

- 4K 母版：`output/wallpapers_pbr/`
- Three.js 优化运行时：`viewer/public/assets/wallpapers/`
- 生成清单与哈希：`viewer/public/assets/manifests/wallpaper_manifest.json`
- 系统说明：`docs/WALLPAPER_SYSTEM.md`

## 2026-08-09 多样性扩展第一批

以下四款继续使用 Codex 内置 ImageGen，每款单独调用。共同要求为：原创、正交平面扫描、四边可连续、均匀漫射、无方向光/阴影/高光/透视/景深、无室内场景、无文字、品牌、商标或水印。PBR 光照不烘焙进 Base Color。

### 09 留白墨枝

源文件：`output/imagegen/wallpaper-ink-branch-generated-v1.png`

```text
Create an original seamless large-repeat premium wallpaper composed of a few quiet ink-wash branch silhouettes, sparse asymmetric leaves, softened dry-brush edges, and generous open negative space. Use warm gray-white paper, soft charcoal-gray, smoke-taupe and a restrained trace of olive-gray. Suggest contemporary East Asian restraint without copying traditional paintings or any named artist. No calligraphy, seals, birds, bamboo clichés, cherry blossoms, framed composition or dramatic black ink.
```

### 10 琥珀构成

源文件：`output/imagegen/wallpaper-midcentury-blocks-generated-v1.png`

```text
Create an original seamless mid-century modern wallpaper using rounded rectangles, slim arcs, offset semicircles and irregular color fields. Use warm oatmeal paper, muted amber, moss green, smoke blue, dusty clay and restrained charcoal. Keep handcrafted screen-print softness and a sophisticated residential scale. Avoid Bauhaus replicas, Memphis style, named designer patterns, primary-color clichés, thick black outlines, optical illusions and 3D blocks.
```

### 11 海岸木刻叶

源文件：`output/imagegen/wallpaper-mediterranean-blockprint-generated-v1.png`

```text
Create an original seamless Mediterranean-inspired block-print wallpaper with simplified olive-like leaves, small abstract seed fruits, curved stems and occasional tiny star-flower shapes. Use a chalky lime-white base, muted olive, dusty indigo, pale terracotta and soft umber. Keep a loose airy half-drop rhythm and slight ink-pressure variation. Avoid William Morris imitation, Provence fabric, tiny cottage florals, lemons, copied ceramic patterns, symmetrical vines and tropical leaves.
```

### 12 夜幕扇影

源文件：`output/imagegen/wallpaper-art-deco-fan-generated-v1.png`

```text
Create an original seamless Art Deco–inspired wallpaper using narrow fan shapes, stepped arcs, elongated scallops and disciplined vertical geometry. Use a deep ink blue-black base, fine muted antique-brass printed ink, shadowy slate blue and tiny warm-stone accents. Brass must remain a flat printed color, not reflective foil. Avoid recognizable archival patterns, Gatsby clichés, metallic foil, gold glitter, palace ornament, peacock feathers and theatrical hotel styling.
```

## 2026-08-09 D1 高差异扩展

共同约束：原创、正视平面材质、均匀漫反射、无场景边缘、无透视、无方向光、无高光、无文字/品牌/水印。每个资产单独生成，再由确定性脚本派生 PBR。

### 13 夜幕植物

源文件：`output/imagegen/wallpaper_nocturne_botanical_generated_v1.png`

深墨绿到蓝黑纸基上的大尺度原创叶片与枝影，低明度、低饱和、非热带写实插画；作为深色沉浸式锚点，同时保留足够负空间。

### 14 氧化色域壁画

源文件：`output/imagegen/wallpaper_oxide_colourfield_generated_v1.png`

为 4.40×2.80m 整墙设计的非循环壁画，以氧化铁、灰粉、烟蓝和矿物米色形成大尺度水平色域与侵蚀边界；禁止可识别地景和小尺度重复。

### 15 纤维涟漪浮雕

源文件：`output/imagegen/wallpaper_fiber_relief_ripple_generated_v1.png`

暖象牙植物纤维纸基上的浅浮雕涟漪，依靠真实微表面而非颜色图案形成差异；正式 PBR 使用 `sculptural_fiber_relief` profile 放大中频 Height/Normal，Base Color 保持无烘焙光照。

## 2026-08-09 D2 缺口扩展

### 16 墨蓝深草编

源文件：`output/imagegen/wallpaper_dark_grasscloth_generated_v1.png`

```text
Use case: stylized-concept
Asset type: project-owned seamless material source for a physically based 3D interior wallpaper
Primary request: create a square, straight-on orthographic diffuse-color source texture of very dark charcoal with a subtle ink-blue undertone natural grasscloth wallpaper, made from fine irregular plant fibers and restrained horizontal and vertical weave
Style/medium: highly realistic architectural material texture, not a room photograph
Composition/framing: surface fills the entire square edge to edge; uniform scale; no border; no central motif; no isolated focal fibers
Lighting/mood: perfectly flat neutral diffuse reference lighting with no directional illumination
Materials/textures: fine dry grass fibers, low contrast, matte, sophisticated and quiet, tiny natural irregularities, dense enough for full-wall use without visual noise
Constraints: seamless/tileable appearance; front-facing orthographic surface; no perspective; no depth-of-field; no cast shadow; no directional shadow; no specular highlight; no gradient; no vignette; no folds; no wall corner; no furniture; no text; no logo; no watermark; original generic material with no brand association
Avoid: black crushed detail, glossy fabric, velvet, linen folds, large stripes, obvious repeating motif, photographic lighting
```
