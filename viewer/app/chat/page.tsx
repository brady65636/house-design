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

type ToolCallInfo = {
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
      content: string;
      streaming: boolean;
      toolCalls: ToolCallInfo[];
      error?: string | null;
    }
  | { id: string; kind: "note"; text: string };

type StoredSession = { id: string; title: string; createdAt: string };

// ---------------------------------------------------------------------------
// 常量与工具函数
// ---------------------------------------------------------------------------

const SESSIONS_KEY = "house-design.chat.sessions";
const CURRENT_KEY = "house-design.chat.current";

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
      const toolCalls: ToolCallInfo[] = (
        Array.isArray(message.tool_calls) ? message.tool_calls : []
      ).map((call) => {
        const c = call as { id?: string; name?: string; args?: unknown };
        return {
          id: String(c.id ?? ""),
          tool: c.name ?? "tool",
          args: stringifyArgs(c.args),
          status: "done" as const,
        };
      });
      if (!content && toolCalls.length === 0) continue;
      items.push({
        id: nextId(),
        kind: "assistant",
        content,
        streaming: false,
        toolCalls,
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
  const [sessions, setSessions] = useState<StoredSession[]>(() =>
    loadStored<StoredSession[]>(SESSIONS_KEY, []),
  );
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(() =>
    loadCurrentId(),
  );
  const [items, setItems] = useState<ChatItem[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  // 右侧嵌入式 3D 视图：保持浏览器渲染会话在线，observe_room 等视觉工具才能用。
  // iframe 始终挂载（隐藏只是 display:none），切换不会让渲染会话掉线。
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
      const id = loadCurrentId();
      if (!id) {
        setHistoryLoaded(true);
        return;
      }
      try {
        const response = await fetch(
          `/chat-proxy/sessions/${encodeURIComponent(id)}/messages`,
          { cache: "no-store" },
        );
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = (await response.json()) as {
          messages: Array<Record<string, unknown>>;
        };
        if (cancelled) return;
        setCurrentSessionId(id);
        setItems(serializeHistory(data.messages ?? []));
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

  const loadMessages = useCallback(async (threadId: string) => {
    const response = await fetch(
      `/chat-proxy/sessions/${encodeURIComponent(threadId)}/messages`,
      { cache: "no-store" },
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = (await response.json()) as {
      messages: Array<Record<string, unknown>>;
    };
    setItems(serializeHistory(data.messages ?? []));
  }, []);

  const createSession = useCallback(async (): Promise<StoredSession> => {
    const response = await fetch("/chat-proxy/sessions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`HTTP ${response.status} ${text.slice(0, 160)}`);
    }
    const data = (await response.json()) as { thread_id: string };
    return {
      id: data.thread_id,
      title: "新对话",
      createdAt: new Date().toISOString(),
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
        await loadMessages(threadId);
      } catch (error) {
        setLoadError(error instanceof Error ? error.message : String(error));
      }
    },
    [currentSessionId, isStreaming, loadMessages],
  );

  const newConversation = useCallback(async () => {
    if (isStreaming) return;
    try {
      const session = await createSession();
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
  }, [isStreaming, createSession]);

  const deleteSession = useCallback(
    async (threadId: string) => {
      if (isStreaming) return;
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
        `/chat-proxy/sessions/${encodeURIComponent(threadId)}`,
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
          session = await createSession();
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
        content: "",
        streaming: true,
        toolCalls: [],
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
                if (item.kind === "assistant") item.content += delta;
              }),
            onToolCall: (id, tool, args) =>
              updateItem(assistantId, (item) => {
                if (item.kind === "assistant") {
                  item.toolCalls.push({
                    id,
                    tool,
                    args: stringifyArgs(args),
                    status: "running",
                  });
                }
              }),
            onToolResult: (id, summary) =>
              updateItem(assistantId, (item) => {
                if (item.kind === "assistant") {
                  const call = item.toolCalls.find((c) => c.id === id);
                  if (call) {
                    call.status = "done";
                    call.summary = truncate(summary, 300);
                  }
                }
              }),
            onDone: (reply) =>
              updateItem(assistantId, (item) => {
                if (item.kind === "assistant") {
                  item.content = reply;
                  item.streaming = false;
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
          <Link className="chat-back-link" href="/">
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
                {item.streaming && !item.content && item.toolCalls.length === 0 && (
                  <span className="chat-typing" aria-label="正在思考">
                    正在思考
                    <i />
                    <i />
                    <i />
                  </span>
                )}
                {item.content && <p className="chat-text">{item.content}</p>}
                {item.toolCalls.length > 0 && (
                  <div className="chat-tools">
                    {item.toolCalls.map((call, index) => (
                      <div className="chat-tool" key={`${call.id}-${index}`}>
                        <span className={`chat-tool-state ${call.status}`}>
                          {call.status === "running" ? "…" : "✓"}
                        </span>
                        <span className="chat-tool-name">{call.tool}</span>
                        <span className="chat-tool-args">{call.args}</span>
                        {call.summary && (
                          <span className="chat-tool-summary">{call.summary}</span>
                        )}
                      </div>
                    ))}
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
          <iframe src="/" title="3D 实时视图" />
        </div>
      </div>
    </main>
  );
}
