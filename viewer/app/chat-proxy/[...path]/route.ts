import type { NextRequest } from "next/server";

// 服务端代理：把浏览器对聊天/会话接口的调用转发到 agent-api 容器。
//
// 为什么需要它：agent-api 的 /api/chat、/api/chat/stream、/api/sessions 都要
// Bearer token（防止陌生人烧 OpenAI token）。token 若打进浏览器 bundle 就形同
// 公开，所以这里让 house-viewer(Node) 在服务端注入 token，浏览器永远拿不到。
//
// 路径映射：/chat-proxy/chat/stream -> {AGENT_API_UPSTREAM}/api/chat/stream
// 部署时在 house-viewer 的 systemd 服务里配 AGENT_API_TOKEN（见 deploy/aws/README.md）。
// 本地开发后端默认关闭鉴权，token 为空时不带 Authorization 头，直接透传。

const AGENT_API_UPSTREAM =
  process.env.AGENT_API_UPSTREAM ?? "http://127.0.0.1:8000";
const AGENT_API_TOKEN = process.env.AGENT_API_TOKEN ?? "";

export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ path: string[] }> };

async function handle(request: NextRequest, ctx: RouteContext): Promise<Response> {
  const { path } = await ctx.params;
  const { search } = new URL(request.url);
  const target = `${AGENT_API_UPSTREAM}/api/${path.join("/")}${search}`;

  const headers: Record<string, string> = {};
  if (AGENT_API_TOKEN) {
    headers.authorization = `Bearer ${AGENT_API_TOKEN}`;
  }
  const contentType = request.headers.get("content-type");
  if (contentType) headers["content-type"] = contentType;

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
  // SSE 透传：禁止中间代理缓冲，保证 message_delta 实时到达浏览器。
  if (hasBody) {
    responseHeaders["x-accel-buffering"] = "no";
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export { handle as GET, handle as POST, handle as DELETE };
