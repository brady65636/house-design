"use client";

// /chat 对话页：与设计 agent 流式聊天。
//
// 数据通路（同域，无 CORS）：
//   浏览器 -> /chat-proxy/...(本机 house-viewer 服务端注入 token)
//          -> agent-api(Docker:8000) /api/chat/stream (SSE)
//
// 功能：
//   - SSE 流式回复（message_delta）+ 工具调用实时提示（tool_call / tool_result）
//   - 会话持久化到 localStorage，可新建/切换/删除会话，历史从后端恢复
//   - 视觉观察工具（observe_room 等）依赖「3D 查看器」页面注册的渲染会话，
//     因此页面底部有提示：观察类需求需另开一个标签页打开主页。

import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

// ---------------------------------------------------------------------------
// 类型
// ---------------------------------------------------------------------------

// 一条 assistant 回复 = 按流式到达顺序排列的「文本 / 工具调用」块。
// 文本增量追加到末尾的 text 块;工具调用各自成一个 tool 块,保持真实时序,
// 不再把文字全部排前、工具调用全部塞到最后。
type AssistantBlock =
  | { kind: "text"; text: string }
  | {
      kind: "tool";
      id: string;
      tool: string;
      args: string;
      status: "running" | "done";
      summary?: string;
    };

type ChatItem =
  | { id: string; kind: "user"; content: string }
  | {
      id: string;
      kind: "assistant";
      blocks: AssistantBlock[];
      streaming: boolean;
      error?: string | null;
    }
  | { id: string; kind: "note"; text: string };

type DesignMode = "fresh" | "branch" | "continue";

type StoredSession = {
  id: string;
  title: string;
  createdAt: string;
  designRunId?: string;
  designMode?: DesignMode;
};

type SessionHistory = {
  messages: Array<Record<string, unknown>>;
  design_run_id?: string | null;
  design_mode?: string | null;
};

function normalizeDesignMode(value: string | null | undefined): DesignMode {
  if (value === "fresh" || value === "branch") return value;
  return "continue";
}

// ---------------------------------------------------------------------------
// 常量与工具函数
// ---------------------------------------------------------------------------

const SESSIONS_KEY = "house-design.chat.sessions";
const CURRENT_KEY = "house-design.chat.current";
// 浏览器级随机身份:同一浏览器内持久,跨浏览器隔离(最小用户隔离,无登录体系)。
// 会话归属到创建它的 client_id;旧的无归属会话(8 月前的历史数据)不出现在任何人列表。
const CLIENT_KEY = "house-design.client_id";

function loadOrCreateClientId(): string {
  try {
    const existing = localStorage.getItem(CLIENT_KEY);
    if (existing && existing.length >= 8) return existing;
    const raw = globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    const id = `client_${raw.replace(/[^a-zA-Z0-9_-]/g, "")}`;
    localStorage.setItem(CLIENT_KEY, id);
    return id;
  } catch {
    return `client_${Date.now().toString(36)}`;
  }
}

function clientIdFromLocationOrStore(): string {
  // 渲染页/iframe 不传时回退到 localStorage;本地开发无 store 时生成一个
  return loadOrCreateClientId();
}

// 工具调用在对话里只展示中文进度名，不暴露原始工具 ID 与 JSON 参数/结果。
const TOOL_LABELS: Record<string, string> = {
  get_today_whether: "查询天气",
  get_room_by_id: "查询房间",
  get_asset_card_by_id: "读取资产卡",
  filter_assets: "筛选候选资产",
  load_scheme: "读取方案",
  observe_room: "观察房间",
  observe_home_harmony: "全屋总览",
  update_scheme: "修改方案",
  ask_design_critic: "独立设计复核",
};

let idCounter = 0;
function nextId(): string {
  idCounter += 1;
  return `msg_${Date.now().toString(36)}_${idCounter}`;
}

function truncate(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max)}…` : value;
}

function stringifyArgs(args: unknown): string {
  try {
    const text =
      typeof args === "string" ? args : JSON.stringify(args, null, 0);
    return truncate(text, 160);
  } catch {
    return String(args);
  }
}

function textFromContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((block) =>
        block && typeof block === "object" && "text" in block
          ? String((block as { text: unknown }).text)
          : "",
      )
      .filter(Boolean)
      .join("\n");
  }
  return "";
}

function loadStored<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function saveStored(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // 隐私模式等场景下忽略持久化失败
  }
}

function loadCurrentId(): string | null {
  try {
    const raw = localStorage.getItem(CURRENT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    return typeof parsed === "string" ? parsed : null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// SSE 流式解析：POST fetch + ReadableStream，逐条分发事件
// ---------------------------------------------------------------------------

async function streamChat(
  threadId: string,
  message: string,
  handlers: {
    onDelta: (delta: string) => void;
    onToolCall: (id: string, tool: string, args: unknown) => void;
    onToolResult: (id: string, summary: string) => void;
    onDone: (reply: string) => void;
    onError: (message: string) => void;
  },
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch("/chat-proxy/chat/stream", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, message }),
    signal,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status} ${text.slice(0, 200)}`);
  }
  if (!response.body) throw new Error("响应没有内容");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE 事件以空行分隔
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      let event = "message";
      let data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      let payload: Record<string, unknown>;
      try {
        payload = JSON.parse(data) as Record<string, unknown>;
      } catch {
        continue;
      }
      switch (event) {
        case "message_delta":
          handlers.onDelta(String(payload.delta ?? ""));
          break;
        case "tool_call":
          handlers.onToolCall(
            String(payload.tool_call_id ?? ""),
            String(payload.tool ?? ""),
            payload.args,
          );
          break;
        case "tool_result":
          handlers.onToolResult(
            String(payload.tool_call_id ?? ""),
            String(payload.summary ?? ""),
          );
          break;
        case "done":
          handlers.onDone(String(payload.reply ?? ""));
          break;
        case "error":
          handlers.onError(String(payload.message ?? "未知错误"));
          break;
      }
    }
  }
}

// ---------------------------------------------------------------------------
// 历史消息反序列化（后端 /sessions/{id}/messages）
// ---------------------------------------------------------------------------

function serializeHistory(messages: Array<Record<string, unknown>>): ChatItem[] {
  const items: ChatItem[] = [];
  for (const message of messages) {
    const role = String(message.role ?? "");
    if (role === "system") continue;
    if (role === "tool") {
      const text = textFromContent(message.content);
      if (text) {
        items.push({
          id: nextId(),
          kind: "note",
          text: `工具返回 · ${truncate(text, 140)}`,
        });
      }
      continue;
    }
    if (role === "user") {
      const text = textFromContent(message.content);
      // 视觉证据等纯图片/合成 user 消息不渲染为气泡
      if (!text) continue;
      items.push({ id: nextId(), kind: "user", content: text });
      continue;
    }
    if (role === "assistant") {
      const content = textFromContent(message.content);
      const toolCalls = (
        Array.isArray(message.tool_calls) ? message.tool_calls : []
      ) as Array<{ id?: string; name?: string; args?: unknown }>;
      const blocks: AssistantBlock[] = [];
      // 单个 assistant 消息内:推理文本在 content,工具调用随后,按此顺序入块;
      // 多个 assistant 消息之间按消息顺序,天然保持交错时序。
      if (content) blocks.push({ kind: "text", text: content });
      for (const call of toolCalls) {
        blocks.push({
          kind: "tool",
          id: String(call.id ?? ""),
          tool: call.name ?? "tool",
          args: stringifyArgs(call.args),
          status: "done",
        });
      }
      if (blocks.length === 0) continue;
      items.push({
        id: nextId(),
        kind: "assistant",
        blocks,
        streaming: false,
      });
    }
  }
  return items;
}

// ---------------------------------------------------------------------------
// 页面组件
// ---------------------------------------------------------------------------

const WELCOME_PROMPTS = [
  "看看客厅现在的设计方案，给我讲讲",
  "主卧墙面换什么颜色好？",
  "厨房选哪种瓷砖更合适？",
  "帮我通观全局，检查全屋搭配是否协调",
];

export default function ChatPage() {
  // Keep the server render and the browser's first render identical. Reading
  // localStorage in a state initializer makes hydration depend on whether this
  // browser already has chat history, while the server always sees an empty
  // store. Restore persisted state only after the component has mounted.
  const [sessions, setSessions] = useState<StoredSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [items, setItems] = useState<ChatItem[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [newSessionMode, setNewSessionMode] = useState<DesignMode>("fresh");
  // 右侧嵌入式 3D 视图：保持浏览器渲染会话在线，observe_room 等视觉工具才能用。
  // iframe 始终挂载；「隐藏」只是把面板移出屏幕（保持盒模型），不会让渲染
  // 会话掉线，也不能用 display:none（那会把 WebGL 画布压到 ~1px，观察截图退化）。
  const [viewerOpen, setViewerOpen] = useState(true);

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const persistSessions = (list: StoredSession[]) =>
    saveStored(SESSIONS_KEY, list);
  const persistCurrent = (id: string | null) =>
    saveStored(CURRENT_KEY, id);

  // 进入页面时恢复当前会话历史
  useEffect(() => {
    let cancelled = false;
    async function restore() {
      const storedSessions = loadStored<StoredSession[]>(SESSIONS_KEY, []);
      const id = loadCurrentId();
      if (cancelled) return;
      // 最小用户隔离:以后端按 client_id 返回的会话列表为权威来源,
      // localStorage 只补充标题/创建时间;旧的无归属会话不再恢复。
      let owned: Array<{ thread_id: string; design_run_id: string | null; design_mode: string | null; bound_at: string }> = [];
      try {
        const clientId = clientIdFromLocationOrStore();
        const response = await fetch(
          `/chat-proxy/sessions?client_id=${encodeURIComponent(clientId)}`,
          { cache: "no-store" },
        );
        if (response.ok) {
          const data = (await response.json()) as {
            sessions: Array<{ thread_id: string; design_run_id: string | null; design_mode: string | null; bound_at: string }>;
          };
          owned = data.sessions ?? [];
        }
      } catch {
        // 列表接口失败时回退到 localStorage(本地开发等无 token 场景)
      }
      const ownedIds = new Set(owned.map((item) => item.thread_id));
      const merged: StoredSession[] = owned.map((item) => {
        const stored = storedSessions.find((session) => session.id === item.thread_id);
        return {
          id: item.thread_id,
          title: stored?.title ?? "历史会话",
          createdAt: stored?.createdAt ?? item.bound_at ?? new Date().toISOString(),
          designRunId: item.design_run_id ?? stored?.designRunId,
          designMode: normalizeDesignMode(item.design_mode ?? stored?.designMode),
        };
      });
      const currentId = id && ownedIds.has(id) ? id : null;
      if (cancelled) return;
      setSessions(merged);
      persistSessions(merged);
      setCurrentSessionId(currentId);
      persistCurrent(currentId);
      if (!currentId) {
        setHistoryLoaded(true);
        return;
      }
      try {
        const clientId = clientIdFromLocationOrStore();
        const response = await fetch(
          `/chat-proxy/sessions/${encodeURIComponent(currentId)}/messages?client_id=${encodeURIComponent(clientId)}`,
          { cache: "no-store" },
        );
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = (await response.json()) as SessionHistory;
        if (cancelled) return;
        setCurrentSessionId(currentId);
        setItems(serializeHistory(data.messages ?? []));
        if (data.design_run_id) {
          setSessions((prev) => {
            const next = prev.map((session) =>
              session.id === currentId
                ? {
                    ...session,
                    designRunId: data.design_run_id ?? undefined,
                    designMode: normalizeDesignMode(data.design_mode),
                  }
                : session,
            );
            persistSessions(next);
            return next;
          });
        }
      } catch (error) {
        if (cancelled) return;
        setLoadError(
          error instanceof Error ? error.message : String(error),
        );
      } finally {
        if (!cancelled) setHistoryLoaded(true);
      }
    }
    void restore();
    return () => {
      cancelled = true;
    };
  }, []);

  // 卸载时中止进行中的请求
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  // 自动滚动到底部
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [items, isStreaming]);

  const updateItem = useCallback(
    (id: string, updater: (item: ChatItem) => void) => {
      setItems((prev) =>
        prev.map((item) => {
          if (item.id !== id) return item;
          const copy: ChatItem = { ...item };
          updater(copy);
          return copy;
        }),
      );
    },
    [],
  );

  const loadMessages = useCallback(async (threadId: string): Promise<SessionHistory> => {
    const clientId = clientIdFromLocationOrStore();
    const response = await fetch(
      `/chat-proxy/sessions/${encodeURIComponent(threadId)}/messages?client_id=${encodeURIComponent(clientId)}`,
      { cache: "no-store" },
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = (await response.json()) as SessionHistory;
    setItems(serializeHistory(data.messages ?? []));
    if (data.design_run_id) {
      setSessions((prev) => {
        const next = prev.map((session) =>
          session.id === threadId
            ? {
                ...session,
                designRunId: data.design_run_id ?? undefined,
                designMode: normalizeDesignMode(data.design_mode),
              }
            : session,
        );
        persistSessions(next);
        return next;
      });
    }
    return data;
  }, []);

  const createSession = useCallback(async (
    mode: DesignMode = "fresh",
    sourceDesignRunId?: string,
  ): Promise<StoredSession> => {
    const clientId = clientIdFromLocationOrStore();
    const response = await fetch("/chat-proxy/sessions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        mode,
        source_design_run_id: mode === "fresh" ? undefined : sourceDesignRunId,
        client_id: clientId,
      }),
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`HTTP ${response.status} ${text.slice(0, 160)}`);
    }
    const data = (await response.json()) as {
      thread_id: string;
      created_at: string;
      design_run_id: string;
      design_mode: DesignMode;
    };
    return {
      id: data.thread_id,
      title: "新对话",
      createdAt: data.created_at ?? new Date().toISOString(),
      designRunId: data.design_run_id,
      designMode: data.design_mode,
    };
  }, []);

  const switchSession = useCallback(
    async (threadId: string) => {
      if (threadId === currentSessionId || isStreaming) return;
      abortRef.current?.abort();
      setCurrentSessionId(threadId);
      persistCurrent(threadId);
      setLoadError(null);
      try {
        const data = await loadMessages(threadId);
        if (data.design_run_id) {
          await fetch(
            `/chat-proxy/design-runs/${encodeURIComponent(data.design_run_id)}/activate`,
            { method: "POST" },
          );
        }
      } catch (error) {
        setLoadError(error instanceof Error ? error.message : String(error));
      }
    },
    [currentSessionId, isStreaming, loadMessages],
  );

  const newConversation = useCallback(async () => {
    if (isStreaming) return;
    try {
      const source = sessions.find((item) => item.id === currentSessionId)?.designRunId;
      const session = await createSession(newSessionMode, source);
      setSessions((prev) => {
        const next = [session, ...prev];
        persistSessions(next);
        return next;
      });
      setCurrentSessionId(session.id);
      persistCurrent(session.id);
      setItems([]);
      setLoadError(null);
      inputRef.current?.focus();
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : String(error));
    }
  }, [isStreaming, createSession, currentSessionId, newSessionMode, sessions]);

  const deleteSession = useCallback(
    async (threadId: string) => {
      if (isStreaming) return;
      const clientId = clientIdFromLocationOrStore();
      setSessions((prev) => {
        const next = prev.filter((s) => s.id !== threadId);
        persistSessions(next);
        return next;
      });
      if (threadId === currentSessionId) {
        setCurrentSessionId(null);
        persistCurrent(null);
        setItems([]);
      }
      await fetch(
        `/chat-proxy/sessions/${encodeURIComponent(threadId)}?client_id=${encodeURIComponent(clientId)}`,
        { method: "DELETE" },
      ).catch(() => undefined);
    },
    [isStreaming, currentSessionId],
  );

  const sendMessage = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || isStreaming) return;

      let threadId = currentSessionId;
      let session = sessions.find((s) => s.id === threadId);
      if (!threadId || !session) {
        try {
          session = await createSession("fresh");
          threadId = session.id;
          setSessions((prev) => {
            const next = [session!, ...prev];
            persistSessions(next);
            return next;
          });
          setCurrentSessionId(threadId);
          persistCurrent(threadId);
        } catch (error) {
          setLoadError(
            error instanceof Error ? error.message : String(error),
          );
          return;
        }
      }
      // 首条消息后把会话标题更新为提问摘要
      if (session && session.title === "新对话" && items.length === 0) {
        setSessions((prev) => {
          const next = prev.map((s) =>
            s.id === session!.id ? { ...s, title: truncate(text, 20) } : s,
          );
          persistSessions(next);
          return next;
        });
      }

      const userItem: ChatItem = {
        id: nextId(),
        kind: "user",
        content: text,
      };
      const assistantId = nextId();
      const assistantItem: ChatItem = {
        id: assistantId,
        kind: "assistant",
        blocks: [],
        streaming: true,
      };
      setItems((prev) => [...prev, userItem, assistantItem]);
      setInput("");
      setIsStreaming(true);
      setLoadError(null);

      const controller = new AbortController();
      abortRef.current = controller;
      try {
        await streamChat(
          threadId,
          text,
          {
            onDelta: (delta) =>
              updateItem(assistantId, (item) => {
                if (item.kind !== "assistant") return;
                // 文本增量追加到末尾的 text 块;若末尾是工具调用块,新起文本块,
                // 保证「工具调用之后又来文本」时按真实顺序展示。
                const last = item.blocks[item.blocks.length - 1];
                if (last && last.kind === "text") {
                  last.text += delta;
                } else {
                  item.blocks.push({ kind: "text", text: delta });
                }
              }),
            onToolCall: (id, tool, args) =>
              updateItem(assistantId, (item) => {
                if (item.kind !== "assistant") return;
                item.blocks.push({
                  kind: "tool",
                  id,
                  tool,
                  args: stringifyArgs(args),
                  status: "running",
                });
              }),
            onToolResult: (id, summary) =>
              updateItem(assistantId, (item) => {
                if (item.kind !== "assistant") return;
                const call = item.blocks.find(
                  (block): block is Extract<AssistantBlock, { kind: "tool" }> =>
                    block.kind === "tool" && block.id === id,
                );
                if (call) {
                  call.status = "done";
                  call.summary = truncate(summary, 300);
                }
              }),
            onDone: (reply) =>
              updateItem(assistantId, (item) => {
                if (item.kind !== "assistant") return;
                item.streaming = false;
                // deliver / stopped 等非 agent 节点的最终回复不经过 message_delta,
                // 只出现在 done.reply;若末尾不是文本块,补成最后一段文本。
                const last = item.blocks[item.blocks.length - 1];
                if (reply && (!last || last.kind !== "text")) {
                  item.blocks.push({ kind: "text", text: reply });
                }
              }),
            onError: (message) =>
              updateItem(assistantId, (item) => {
                if (item.kind === "assistant") {
                  item.error = message;
                  item.streaming = false;
                }
              }),
          },
          controller.signal,
        );
      } catch (error) {
        const message =
          error instanceof DOMException && error.name === "AbortError"
            ? "已停止生成"
            : error instanceof Error
              ? error.message
              : String(error);
        updateItem(assistantId, (item) => {
          if (item.kind === "assistant") {
            item.error = message;
            item.streaming = false;
          }
        });
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [currentSessionId, sessions, items.length, isStreaming, createSession, updateItem],
  );

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage(input);
    }
  };

  const isEmpty = items.length === 0;
  const currentSession = sessions.find((session) => session.id === currentSessionId);
  const viewerHref = currentSession?.designRunId
    ? `/?design_run_id=${encodeURIComponent(currentSession.designRunId)}`
    : "/";

  return (
    <main className="chat-page">
      <header className="chat-header">
        <div className="chat-brand">
          <span>H</span>
          <div>
            <small>HOUSE DESIGN LAB</small>
            <strong>设计助手</strong>
          </div>
        </div>

        <div className="chat-session-ctl">
          <select
            className="chat-mode-select"
            value={newSessionMode}
            disabled={isStreaming}
            title="决定“新对话”如何获得设计起点"
            onChange={(event) => setNewSessionMode(event.target.value as DesignMode)}
          >
            <option value="fresh">从零设计（默认）</option>
            <option value="branch">复制当前为独立分支</option>
            <option value="continue">新对话继续当前方案</option>
          </select>
          <label className="chat-session-select-wrap">
            <select
              className="chat-session-select"
              value={currentSessionId ?? ""}
              disabled={isStreaming}
              onChange={(event) => void switchSession(event.target.value)}
            >
              {sessions.length === 0 && (
                <option value="">新对话</option>
              )}
              {sessions.map((session) => (
                <option key={session.id} value={session.id}>
                  {truncate(session.title, 24)}
                </option>
              ))}
            </select>
            {currentSessionId && sessions.length > 0 && (
              <button
                type="button"
                className="chat-session-delete"
                title="删除当前会话"
                disabled={isStreaming}
                onClick={() => void deleteSession(currentSessionId)}
              >
                删除
              </button>
            )}
          </label>
          <button
            type="button"
            className="chat-new-btn"
            disabled={isStreaming}
            onClick={() => void newConversation()}
          >
            ＋ 新对话
          </button>
          <button
            type="button"
            className={`chat-viewer-toggle${viewerOpen ? " active" : ""}`}
            onClick={() => setViewerOpen((open) => !open)}
          >
            {viewerOpen ? "隐藏 3D 视图" : "显示 3D 视图"}
          </button>
          <Link className="chat-back-link" href={viewerHref}>
            返回 3D 查看
          </Link>
        </div>
      </header>

      <div className="chat-body">
        <div className="chat-left">
          <div className="chat-main" ref={scrollRef}>
        {loadError && <p className="chat-error-banner">{loadError}</p>}

        {isEmpty && historyLoaded && !loadError && (
          <section className="chat-welcome">
            <h1>和设计助手聊聊</h1>
            <p>
              我可以帮你了解房间现状、挑选材料、检查全屋搭配，
              也可以直接修改设计方案。试试下面这些：
            </p>
            <div className="chat-welcome-prompts">
              {WELCOME_PROMPTS.map((prompt) => (
                <button
                  type="button"
                  key={prompt}
                  disabled={isStreaming}
                  onClick={() => void sendMessage(prompt)}
                >
                  {prompt}
                </button>
              ))}
            </div>
          </section>
        )}

        {items.map((item) => {
          if (item.kind === "note") {
            return (
              <p className="chat-note" key={item.id}>
                {item.text}
              </p>
            );
          }
          if (item.kind === "user") {
            return (
              <div className="chat-row chat-row-user" key={item.id}>
                <div className="chat-bubble chat-bubble-user">
                  {item.content}
                </div>
              </div>
            );
          }
          return (
            <div className="chat-row chat-row-assistant" key={item.id}>
              <div
                className={`chat-bubble chat-bubble-assistant${item.error ? " chat-bubble-error" : ""}`}
              >
                {item.streaming && item.blocks.length === 0 && (
                  <span className="chat-typing" aria-label="正在思考">
                    正在思考
                    <i />
                    <i />
                    <i />
                  </span>
                )}
                {item.blocks.length > 0 && (
                  <div className="chat-blocks">
                    {item.blocks.map((block, index) =>
                      block.kind === "text" ? (
                        <div className="chat-text" key={index}>
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              a: ({ node, ...props }) => (
                                <a {...props} target="_blank" rel="noopener noreferrer" />
                              ),
                            }}
                          >
                            {block.text}
                          </ReactMarkdown>
                        </div>
                      ) : (
                        <div className="chat-tool" key={`${block.id}-${index}`}>
                          <span className={`chat-tool-state ${block.status}`}>
                            {block.status === "running" ? "…" : "✓"}
                          </span>
                          <span className="chat-tool-name">
                            {TOOL_LABELS[block.tool] ?? block.tool}
                          </span>
                        </div>
                      ),
                    )}
                  </div>
                )}
                {item.error && <p className="chat-error">{item.error}</p>}
              </div>
            </div>
          );
        })}
      </div>

      <footer className="chat-input-bar">
        <p className="chat-hint">
          右侧是实时 3D 视图，渲染会话保持在线：让 agent 观察房间（如“看看客厅”）时可直接使用，
          方案修改后视图会自动同步；也可点「隐藏 3D 视图」聚焦聊天。
        </p>
        <div className="chat-input-row">
          <textarea
            ref={inputRef}
            className="chat-textarea"
            rows={2}
            placeholder="输入你的问题，Enter 发送，Shift+Enter 换行"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={onKeyDown}
            disabled={isStreaming}
          />
          <button
            type="button"
            className="chat-send"
            disabled={isStreaming || !input.trim()}
            onClick={() => void sendMessage(input)}
          >
            {isStreaming ? "…" : "发送"}
          </button>
        </div>
      </footer>
        </div>

        <div className={`chat-viewer${viewerOpen ? "" : " chat-viewer-hidden"}`}>
          <iframe key={viewerHref} src={viewerHref} title="3D 实时视图" />
        </div>
      </div>
    </main>
  );
}
