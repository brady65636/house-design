import type { NextRequest } from "next/server";

// 服务端代理：把浏览器对渲染桥的调用（/bridge/...）转发到 render-bridge。
//
// 为什么需要它：observe_room / observe_home_harmony 由「用户浏览器」执行截图，
// 前端 bridge worker 默认向 ${origin}/bridge 注册会话并轮询命令。本地没有 nginx
// 反代 /bridge（生产由 nginx 接管 /bridge -> render-bridge:8765），所以这里让
// house-viewer(Node) 直接转发到 render-bridge，前端无需带 ?render_bridge= 参数。
//
// 路径映射：/bridge/v1/render-sessions/... -> {RENDER_BRIDGE_UPSTREAM}/v1/render-sessions/...
// 生产同域：nginx 会先命中 /bridge，本路由不会被调用，天然休眠无副作用。

const RENDER_BRIDGE_UPSTREAM =
  process.env.RENDER_BRIDGE_UPSTREAM ?? "http://127.0.0.1:8765";

export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ path: string[] }> };

async function handle(request: NextRequest, ctx: RouteContext): Promise<Response> {
  const { path } = await ctx.params;
  const { search } = new URL(request.url);
  const target = `${RENDER_BRIDGE_UPSTREAM}/${path.join("/")}${search}`;

  const headers: Record<string, string> = {};
  const contentType = request.headers.get("content-type");
  if (contentType) headers["content-type"] = contentType;

  // 观察结果可能包含多张 base64 截图（几百 KB），按文本整体透传即可。
  const hasBody = request.method === "POST";
  const upstream = await fetch(target, {
    method: request.method,
    headers,
    body: hasBody ? await request.text() : undefined,
    signal: request.signal,
    cache: "no-store",
  });

  const responseHeaders: Record<string, string> = {
    "content-type": upstream.headers.get("content-type") ?? "application/json",
    "cache-control": upstream.headers.get("cache-control") ?? "no-cache",
  };
  if (hasBody) {
    responseHeaders["x-accel-buffering"] = "no";
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export { handle as GET, handle as POST, handle as OPTIONS };
