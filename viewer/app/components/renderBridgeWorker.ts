// Command polling for the render bridge, run in a Web Worker.
//
// Why a Worker: Chrome throttles timers in a *hidden* tab down to roughly one
// per minute, which used to starve the bridge's online-freshness window and
// delay command delivery.  Worker timers are NOT subject to that hidden-tab
// throttling, so this file keeps a lightweight poll alive even when the tab is
// backgrounded. A successful command poll already refreshes the bridge's online
// timestamp, so a separate heartbeat would only double the request rate. The
// Worker only does network I/O; rendering stays on the main thread because the
// WebGL renderer lives there.
//
// tsconfig only includes the `dom` lib, so avoid the `webworker` global: type
// the Worker scope locally instead.

type BridgeWorkerScope = {
  onmessage: ((event: MessageEvent<unknown>) => void) | null;
  postMessage: (message: unknown) => void;
};

const scope = self as unknown as BridgeWorkerScope;

type InitMessage = { type: "init"; sessionId: string; bridgeUrl: string };

type BridgeCommand = {
  id: string;
  tool: "observe_room" | "observe_home_harmony";
  args: { room_id?: string; focus_target_ids?: string[]; design_run_id?: string };
};

let sessionId = "";
let bridgeUrl = "";
let started = false;

scope.onmessage = (event: MessageEvent<unknown>) => {
  const message = event.data as InitMessage;
  if (message?.type !== "init") return;
  sessionId = message.sessionId;
  bridgeUrl = message.bridgeUrl.replace(/\/$/, "");
  if (started) return;
  started = true;
  // Chained setTimeout keeps poll cadence strictly serial.
  void tick();
};

const pollCommands = async (): Promise<void> => {
  if (!sessionId || !bridgeUrl) return;
  try {
    const response = await fetch(`${bridgeUrl}/v1/render-sessions/${encodeURIComponent(sessionId)}/commands`, {
      cache: "no-store",
    });
    if (response.status === 204) return;
    if (!response.ok) throw new Error(`render_command_poll_${response.status}`);
    const command = (await response.json()) as BridgeCommand;
    scope.postMessage({ type: "command", command });
  } catch (error) {
    // A disconnected bridge must not destabilize the interactive viewer.
    scope.postMessage({ type: "warning", message: error instanceof Error ? error.message : String(error) });
  }
};

const tick = async (): Promise<void> => {
  await pollCommands();
  setTimeout(() => void tick(), 2_000);
};
