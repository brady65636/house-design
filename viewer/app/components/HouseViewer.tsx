"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

type LoadState = "loading" | "ready" | "error";

type SelectedSurface = {
  surfaceId: string;
  role: string;
  assetId: string | null;
  objectName: string;
};

type AssetEntry = {
  id: string;
  category: string;
  brief: string;
};

type ViewerApi = {
  resetCamera: () => void;
  setAutoRotate: (value: boolean) => void;
  setCutaway: (value: boolean) => void;
  setCeilings: (value: boolean) => void;
  applyAsset: (surfaceIds: string[], assetId: string) => void;
  applyWallBase: (assetId: string) => void;
};

const FLOOR_TARGETS = [
  "surface_real4_floor_open_public",
  "surface_real4_floor_dining_room",
];

const ASSET_COLORS: Record<string, string> = {
  paint_warm_white_01: "#F5F2EB",
  paint_greige_01: "#E5DDD1",
  wallpaper_linen_natural_01: "#c9b99f",
  wallpaper_linear_geometry_01: "#c6bba7",
  floor_light_oak_matte_01: "#c89c63",
  floor_honey_oak_matte_01: "#a8662e",
  tile_warm_travertine_01: "#b69d77",
  tile_light_microcement_01: "#9ea19d",
};

function seeded(seed: number) {
  let value = seed >>> 0;
  return () => {
    value = (value * 1664525 + 1013904223) >>> 0;
    return value / 4294967296;
  };
}

function makePatternTexture(assetId: string) {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const context = canvas.getContext("2d");
  if (!context) return null;

  const base = ASSET_COLORS[assetId] ?? "#b7b2a8";
  context.fillStyle = base;
  context.fillRect(0, 0, 512, 512);
  const random = seeded(
    Array.from(assetId).reduce((sum, character) => sum + character.charCodeAt(0), 0),
  );

  if (assetId.startsWith("floor_")) {
    context.lineCap = "round";
    for (let index = 0; index < 150; index += 1) {
      const y = random() * 512;
      const amplitude = 2 + random() * 8;
      context.beginPath();
      context.moveTo(0, y);
      for (let x = 0; x <= 512; x += 24) {
        context.lineTo(x, y + Math.sin(x * 0.025 + random() * 3) * amplitude);
      }
      context.strokeStyle = `rgba(72, 38, 16, ${0.025 + random() * 0.08})`;
      context.lineWidth = 0.5 + random() * 1.4;
      context.stroke();
    }
    context.strokeStyle = "rgba(49, 27, 13, 0.22)";
    context.lineWidth = 2;
    for (let y = 0; y <= 512; y += 128) {
      context.beginPath();
      context.moveTo(0, y);
      context.lineTo(512, y);
      context.stroke();
    }
    context.strokeStyle = "rgba(255, 245, 222, 0.10)";
    for (let row = 0; row < 4; row += 1) {
      const offset = row % 2 === 0 ? 192 : 64;
      context.beginPath();
      context.moveTo(offset, row * 128);
      context.lineTo(offset, (row + 1) * 128);
      context.stroke();
    }
  } else if (assetId === "wallpaper_linen_natural_01") {
    context.lineWidth = 1;
    for (let position = 0; position < 512; position += 5) {
      context.strokeStyle = `rgba(66, 50, 31, ${0.04 + random() * 0.06})`;
      context.beginPath();
      context.moveTo(position, 0);
      context.lineTo(position + random() * 3, 512);
      context.stroke();
      context.beginPath();
      context.moveTo(0, position);
      context.lineTo(512, position + random() * 3);
      context.stroke();
    }
  } else if (assetId === "wallpaper_linear_geometry_01") {
    for (let x = 0; x < 512; x += 24) {
      context.fillStyle = x % 48 === 0 ? "rgba(69, 57, 41, 0.22)" : "rgba(255,255,255,0.14)";
      context.fillRect(x, 0, 3, 512);
    }
  } else if (assetId.startsWith("tile_")) {
    const image = context.getImageData(0, 0, 512, 512);
    for (let index = 0; index < image.data.length; index += 4) {
      const noise = Math.round((random() - 0.5) * 22);
      image.data[index] = Math.max(0, Math.min(255, image.data[index] + noise));
      image.data[index + 1] = Math.max(0, Math.min(255, image.data[index + 1] + noise));
      image.data[index + 2] = Math.max(0, Math.min(255, image.data[index + 2] + noise));
    }
    context.putImageData(image, 0, 0);
    context.strokeStyle = "rgba(44, 43, 39, 0.24)";
    context.lineWidth = 3;
    context.strokeRect(1.5, 1.5, 509, 509);
    if (assetId.includes("travertine")) {
      for (let index = 0; index < 18; index += 1) {
        const y = random() * 512;
        context.beginPath();
        context.moveTo(0, y);
        context.bezierCurveTo(150, y + random() * 22, 340, y - random() * 22, 512, y + 5);
        context.strokeStyle = `rgba(91, 69, 41, ${0.035 + random() * 0.05})`;
        context.lineWidth = 1 + random() * 3;
        context.stroke();
      }
    }
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(
    assetId.startsWith("wallpaper_") ? 4 : assetId.startsWith("floor_") ? 3 : 2,
    assetId.startsWith("floor_") ? 4 : 3,
  );
  texture.anisotropy = 8;
  return texture;
}

function buildMaterialLibrary() {
  const library = new Map<string, THREE.MeshStandardMaterial>();
  Object.entries(ASSET_COLORS).forEach(([assetId, color]) => {
    const pattern =
      assetId.startsWith("paint_") ? null : makePatternTexture(assetId);
    const material = new THREE.MeshStandardMaterial({
      name: `WEB_${assetId}`,
      color: pattern ? "#ffffff" : color,
      map: pattern,
      roughness: assetId.includes("eggshell") ? 0.55 : 0.82,
      metalness: 0,
      side: THREE.DoubleSide,
    });
    material.userData.asset_id = assetId;
    library.set(assetId, material);
  });
  return library;
}

function resolveAssetId(material: THREE.Material | THREE.Material[]) {
  const first = Array.isArray(material) ? material[0] : material;
  const fromExtras = first?.userData?.asset_id;
  if (typeof fromExtras === "string") return fromExtras;
  const normalized = first?.name?.replace(/^MAT_/, "").replace(/^WEB_/, "");
  return normalized && ASSET_COLORS[normalized] ? normalized : null;
}

export function HouseViewer() {
  const hostRef = useRef<HTMLDivElement>(null);
  const apiRef = useRef<ViewerApi | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [progress, setProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState("");
  const [autoRotate, setAutoRotate] = useState(false);
  const [cutaway, setCutaway] = useState(true);
  const [ceilings, setCeilings] = useState(false);
  const [floorChoice, setFloorChoice] = useState("floor_light_oak_matte_01");
  const [wallChoice, setWallChoice] = useState("paint_warm_white_01");
  const [selected, setSelected] = useState<SelectedSurface | null>(null);
  const [assets, setAssets] = useState<AssetEntry[]>([]);
  const [stats, setStats] = useState({ meshes: 0, surfaces: 0 });

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let disposed = false;
    let animationFrame = 0;
    let modelRoot: THREE.Group | null = null;
    let selectionHelper: THREE.BoxHelper | null = null;
    let cutawayEnabled = true;
    let ceilingsEnabled = false;
    const materialLibrary = buildMaterialLibrary();
    const surfaceIndex = new Map<string, THREE.Mesh[]>();
    const originalCamera = {
      position: new THREE.Vector3(),
      target: new THREE.Vector3(),
    };

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#111614");
    scene.fog = new THREE.Fog("#111614", 34, 78);

    const camera = new THREE.PerspectiveCamera(38, 1, 0.05, 160);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.9;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.domElement.className = "viewer-canvas";
    renderer.domElement.setAttribute("aria-label", "可交互的室内空间方案查看器");
    host.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.07;
    controls.minDistance = 5;
    controls.maxDistance = 62;
    controls.maxPolarAngle = Math.PI * 0.48;
    controls.autoRotateSpeed = 0.65;

    const hemisphere = new THREE.HemisphereLight("#e9f3ee", "#342d24", 1.8);
    scene.add(hemisphere);
    const key = new THREE.DirectionalLight("#fff0d2", 3.2);
    key.position.set(6, 14, 9);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.camera.left = -16;
    key.shadow.camera.right = 16;
    key.shadow.camera.top = 16;
    key.shadow.camera.bottom = -16;
    scene.add(key);
    const fill = new THREE.DirectionalLight("#bcd7ff", 1.0);
    fill.position.set(-8, 6, -10);
    scene.add(fill);

    const grid = new THREE.GridHelper(44, 44, "#39443f", "#202824");
    grid.position.y = -0.085;
    scene.add(grid);

    const resize = () => {
      const width = Math.max(host.clientWidth, 1);
      const height = Math.max(host.clientHeight, 1);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();

    const applyVisibility = () => {
      if (!modelRoot) return;
      modelRoot.traverse((object) => {
        if (!(object instanceof THREE.Mesh)) return;
        const isContextOnly = object.userData.context_only === true;
        const isCeiling = object.userData.surface_role === "ceiling";
        const isCutawayPart = object.userData.preview_hide === true && !isCeiling;
        object.visible = !isContextOnly
          && (!isCeiling || ceilingsEnabled)
          && (!isCutawayPart || !cutawayEnabled);
      });
    };

    const resetCamera = () => {
      camera.position.copy(originalCamera.position);
      controls.target.copy(originalCamera.target);
      controls.update();
    };

    const applyAsset = (surfaceIds: string[], assetId: string) => {
      const material = materialLibrary.get(assetId);
      if (!material) return;
      surfaceIds.forEach((surfaceId) => {
        surfaceIndex.get(surfaceId)?.forEach((mesh) => {
          mesh.material = material;
          mesh.userData.currentAssetId = assetId;
        });
      });
      setSelected((current) =>
        current && surfaceIds.includes(current.surfaceId)
          ? { ...current, assetId }
          : current,
      );
    };

    const applyWallBase = (assetId: string) => {
      const wallIds = Array.from(surfaceIndex.keys()).filter(
        (surfaceId) => surfaceId.startsWith("wall_face_real4_"),
      );
      applyAsset(wallIds, assetId);
    };

    apiRef.current = {
      resetCamera,
      setAutoRotate: (value) => {
        controls.autoRotate = value;
      },
      setCutaway: (value) => {
        cutawayEnabled = value;
        setCutaway(value);
        applyVisibility();
      },
      setCeilings: (value) => {
        ceilingsEnabled = value;
        setCeilings(value);
        applyVisibility();
      },
      applyAsset,
      applyWallBase,
    };

    fetch("/models/asset_manifest.json")
      .then((response) => response.json())
      .then((manifest: { assets: AssetEntry[] }) => {
        if (!disposed) setAssets(manifest.assets);
      })
      .catch(() => undefined);

    const loader = new GLTFLoader();
    loader.load(
      "/models/house_spacious_yunkuo_135_v4.glb?revision=south-beds-against-wall",
      (gltf) => {
        if (disposed) return;
        modelRoot = gltf.scene;
        modelRoot.name = "house_spacious_yunkuo_135_v4";
        let meshCount = 0;
        const surfaceIds = new Set<string>();

        modelRoot.traverse((object) => {
          if (!(object instanceof THREE.Mesh)) return;
          const isContextOnly = object.userData.context_only === true;
          object.visible = !isContextOnly;
          if (isContextOnly) return;
          meshCount += 1;
          object.castShadow = false;
          object.receiveShadow = true;
          const surfaceId = object.userData.surface_id;
          if (typeof surfaceId === "string") {
            surfaceIds.add(surfaceId);
            const entries = surfaceIndex.get(surfaceId) ?? [];
            entries.push(object);
            surfaceIndex.set(surfaceId, entries);
          }
          const wallFaceId = object.userData.wall_face_id;
          if (typeof wallFaceId === "string") {
            surfaceIds.add(wallFaceId);
            const entries = surfaceIndex.get(wallFaceId) ?? [];
            entries.push(object);
            surfaceIndex.set(wallFaceId, entries);
          }

          const assetId = resolveAssetId(object.material);
          if (assetId && materialLibrary.has(assetId)) {
            object.material = materialLibrary.get(assetId)!;
            object.userData.currentAssetId = assetId;
          }
        });

        scene.add(modelRoot);
        modelRoot.updateMatrixWorld(true);
        const bounds = new THREE.Box3();
        modelRoot.traverse((object) => {
          if (object instanceof THREE.Mesh && object.userData.context_only !== true) {
            bounds.expandByObject(object);
          }
        });
        const center = bounds.getCenter(new THREE.Vector3());
        const size = bounds.getSize(new THREE.Vector3());
        const maximum = Math.max(size.x, size.y, size.z);
        originalCamera.target.copy(center).add(new THREE.Vector3(0, -0.35, 0));
        originalCamera.position.copy(center).add(
          new THREE.Vector3(maximum * 0.92, maximum * 0.78, maximum * 0.88),
        );
        resetCamera();
        applyVisibility();
        setStats({ meshes: meshCount, surfaces: surfaceIds.size });
        setProgress(100);
        setLoadState("ready");
      },
      (event) => {
        if (event.total > 0) {
          setProgress(Math.round((event.loaded / event.total) * 100));
        }
      },
      (error) => {
        console.error(error);
        if (!disposed) {
          setErrorMessage("模型没有成功加载，请刷新页面重试。");
          setLoadState("error");
        }
      },
    );

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const onPointerUp = (event: PointerEvent) => {
      if (!modelRoot || event.button !== 0) return;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const match = raycaster
        .intersectObject(modelRoot, true)
        .find((hit) => hit.object.visible && (
          typeof hit.object.userData.wall_face_id === "string"
          || typeof hit.object.userData.surface_id === "string"
        ));
      if (!match || !(match.object instanceof THREE.Mesh)) return;
      const mesh = match.object;
      const surfaceId = (mesh.userData.wall_face_id ?? mesh.userData.surface_id) as string;
      const materialAsset = mesh.userData.currentAssetId ?? resolveAssetId(mesh.material);
      setSelected({
        surfaceId,
        role: mesh.userData.surface_role ?? "surface",
        assetId: typeof materialAsset === "string" ? materialAsset : null,
        objectName: mesh.name,
      });
      if (selectionHelper) scene.remove(selectionHelper);
      selectionHelper = new THREE.BoxHelper(mesh, "#e5b665");
      selectionHelper.material.depthTest = false;
      selectionHelper.renderOrder = 10;
      scene.add(selectionHelper);
    };
    renderer.domElement.addEventListener("pointerup", onPointerUp);

    const animate = () => {
      controls.update();
      if (selectionHelper) selectionHelper.update();
      renderer.render(scene, camera);
      animationFrame = requestAnimationFrame(animate);
    };
    animate();

    return () => {
      disposed = true;
      cancelAnimationFrame(animationFrame);
      observer.disconnect();
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      controls.dispose();
      renderer.dispose();
      materialLibrary.forEach((material) => {
        material.map?.dispose();
        material.dispose();
      });
      if (host.contains(renderer.domElement)) host.removeChild(renderer.domElement);
      apiRef.current = null;
    };
  }, []);

  const assetName = (assetId: string | null) =>
    assets.find((asset) => asset.id === assetId)?.brief ?? assetId ?? "未标记";

  const chooseFloor = (assetId: string) => {
    setFloorChoice(assetId);
    apiRef.current?.applyAsset(FLOOR_TARGETS, assetId);
  };

  const chooseWall = (assetId: string) => {
    setWallChoice(assetId);
    apiRef.current?.applyWallBase(assetId);
  };

  const toggleAutoRotate = () => {
    const next = !autoRotate;
    setAutoRotate(next);
    apiRef.current?.setAutoRotate(next);
  };

  const toggleCutaway = () => {
    const next = !cutaway;
    setCutaway(next);
    apiRef.current?.setCutaway(next);
  };

  const toggleCeilings = () => {
    const next = !ceilings;
    setCeilings(next);
    apiRef.current?.setCeilings(next);
  };

  return (
    <main className="viewer-shell">
      <section className="stage" aria-label="室内空间方案查看区域">
        <div ref={hostRef} className="canvas-host" />

        <header className="brand-bar">
          <div className="brand-mark">H</div>
          <div>
            <p className="eyebrow">HOUSE DESIGN LAB</p>
            <h1>室内空间方案查看器</h1>
          </div>
          <div className={`connection ${loadState}`}>
            <span />
            {loadState === "ready" ? "模型已连接" : loadState === "error" ? "加载失败" : `加载 ${progress}%`}
          </div>
        </header>

        {loadState !== "ready" && (
          <div className="loading-card" role="status">
            <div className="loading-orbit"><span /></div>
            <p>{loadState === "error" ? errorMessage : "正在加载模型…"}</p>
            {loadState === "loading" && <div className="progress"><i style={{ width: `${progress}%` }} /></div>}
          </div>
        )}

        <div className="view-actions" aria-label="视图控制">
          <button type="button" onClick={() => apiRef.current?.resetCamera()}>归位</button>
          <button type="button" className={autoRotate ? "active" : ""} onClick={toggleAutoRotate}>环绕</button>
          <button type="button" className={cutaway ? "active" : ""} onClick={toggleCutaway}>剖切</button>
          <button type="button" className={ceilings ? "active" : ""} onClick={toggleCeilings}>吊顶</button>
        </div>

        <p className="gesture-hint">拖动旋转 · 滚轮缩放 · 点击表面查看数据</p>
      </section>

      <aside className="inspector" aria-label="方案控制面板">
        <div className="inspector-head">
          <div>
            <p className="eyebrow">LIVE SCHEME</p>
            <h2>温暖自然 · 01</h2>
          </div>
          <span className="version">v0.2</span>
        </div>

        <div className="metrics">
          <div><strong>{stats.surfaces || "—"}</strong><span>可识别表面</span></div>
          <div><strong>{stats.meshes || "—"}</strong><span>模型对象</span></div>
        </div>

        <section className="control-section">
          <div className="section-title">
            <span>01</span>
            <div><h3>地面材质</h3><p>选择地板材质，实时预览效果</p></div>
          </div>
          <div className="swatch-row">
            <button type="button" className={floorChoice.includes("light") ? "selected" : ""} onClick={() => chooseFloor("floor_light_oak_matte_01")}>
              <i className="swatch oak-light" /><span>浅橡木</span>
            </button>
            <button type="button" className={floorChoice.includes("honey") ? "selected" : ""} onClick={() => chooseFloor("floor_honey_oak_matte_01")}>
              <i className="swatch oak-honey" /><span>蜂蜜橡木</span>
            </button>
          </div>
        </section>

        <section className="control-section">
          <div className="section-title">
            <span>02</span>
            <div><h3>墙面基调</h3><p>保留两处墙纸焦点面</p></div>
          </div>
          <div className="swatch-row">
            <button type="button" className={wallChoice === "paint_warm_white_01" ? "selected" : ""} onClick={() => chooseWall("paint_warm_white_01")}>
              <i className="swatch paint-cream" /><span>暖奶油</span>
            </button>
            <button type="button" className={wallChoice.includes("greige") ? "selected" : ""} onClick={() => chooseWall("paint_greige_01")}>
              <i className="swatch paint-greige" /><span>浅 Greige</span>
            </button>
          </div>
        </section>

        <section className="selection-card">
          <div className="selection-label"><span /> 当前表面</div>
          {selected ? (
            <>
              <h3>{selected.surfaceId.replace("surface_", "").replaceAll("_", " / ")}</h3>
              <p>{assetName(selected.assetId)}</p>
              <code>{selected.surfaceId}</code>
            </>
          ) : (
            <div className="empty-selection">
              <strong>点击模型中的地面或墙面</strong>
              <span>这里会显示 Scheme 使用的稳定表面 ID</span>
            </div>
          )}
        </section>

        <footer className="inspector-foot">
          <span>GLB · Z-up → glTF Y-up</span>
          <span>原创代表资产</span>
        </footer>
      </aside>
    </main>
  );
}
