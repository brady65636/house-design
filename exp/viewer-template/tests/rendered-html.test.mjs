import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the room-level camera experience shell", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>房间设计实验室 \| House Design Lab<\/title>/i);
  assert.match(html, /房间设计实验室/);
  assert.match(html, /房间摄像机轨迹/);
  assert.match(html, /横厅客厅/);
  assert.match(html, /南向阳台/);
  assert.match(html, /5 品类 · 87 个资产 \/ 预设/);
  assert.match(html, /墙漆 · 60/);
  assert.match(html, /墙纸 · 8/);
  assert.match(html, /地板 · 6/);
  assert.match(html, /瓷砖 · 8/);
  assert.match(html, /吊顶 · 5/);
  assert.match(html, /雾境层峦壁画/);
  assert.match(html, /role="status"/);
  assert.doesNotMatch(html, /Your site is taking shape|react-loading-skeleton/);
});

test("keeps the production page wired to the catalog-driven experience", async () => {
  const [page, layout, experience, catalog, cameraCatalog] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/RoomExperience.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/data/wallpaperCatalog.json", import.meta.url), "utf8"),
    readFile(new URL("../app/data/roomCameraTracksV4.json", import.meta.url), "utf8"),
  ]);

  assert.match(page, /import \{ RoomExperience \}/);
  assert.match(page, /<RoomExperience \/>/);
  assert.match(layout, /House Design Lab/);
  assert.doesNotMatch(layout, /codex-preview|_sites-preview|Starter Project/);
  assert.match(experience, /import \{ WALLPAPERS \}/);
  assert.match(experience, /WALLPAPERS\.map/);
  assert.equal(JSON.parse(catalog).products.length, 8);
  assert.match(experience, /FLOORS\.map/);
  assert.match(experience, /TILES\.map/);
  assert.match(experience, /CEILINGS\.map/);
  assert.match(experience, /ROOM_CAMERA_TRACKS\.map/);
  assert.equal(JSON.parse(cameraCatalog).tracks.length, 11);
  assert.doesNotMatch(experience, /THREE\.BoxHelper|selectionHelper|depthTest\s*=\s*false/);
});
