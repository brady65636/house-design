import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const chatSource = await readFile(new URL("../app/chat/page.tsx", import.meta.url), "utf8");

test("chat hydration starts from the same session state on server and client", () => {
  assert.match(chatSource, /useState<StoredSession\[\]>\(\[\]\)/);
  assert.match(chatSource, /useState<string \| null>\(null\)/);
  assert.doesNotMatch(
    chatSource,
    /useState<StoredSession\[\]>\(\(\) =>\s*loadStored/,
  );
  assert.doesNotMatch(
    chatSource,
    /useState<string \| null>\(\(\) =>\s*loadCurrentId/,
  );
});

test("persisted chat sessions are restored only after mount", () => {
  const restoreEffect = chatSource.match(
    /useEffect\(\(\) => \{[\s\S]*?async function restore\(\)[\s\S]*?void restore\(\);[\s\S]*?\}, \[\]\);/,
  )?.[0] ?? "";

  assert.match(restoreEffect, /loadStored<StoredSession\[\]>\(SESSIONS_KEY, \[\]\)/);
  assert.match(restoreEffect, /loadCurrentId\(\)/);
  // client_id 最小用户隔离：以后端按 client_id 返回的会话列表为权威来源，
  // 只有属于当前浏览器的会话才被恢复（旧的无归属会话不再出现）。
  assert.match(restoreEffect, /ownedIds\.has\(id\)/);
  assert.match(restoreEffect, /setCurrentSessionId\(currentId\)/);
  assert.match(restoreEffect, /setSessions\(merged\)/);
});
