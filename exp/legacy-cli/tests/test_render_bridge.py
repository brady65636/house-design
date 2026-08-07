import threading
import time
import unittest

from render_bridge import AgentCommandRequest, BrowserResultRequest, RenderTaskBroker


class RenderBridgeTests(unittest.TestCase):
    def test_agent_waits_for_browser_result_from_the_same_session(self) -> None:
        broker = RenderTaskBroker()
        broker.heartbeat("review-session")
        output = []

        def submit() -> None:
            output.append(
                broker.submit(
                    "review-session",
                    AgentCommandRequest(tool="observe_room", args={"room_id": "open_public"}, timeout_ms=5_000),
                )
            )

        thread = threading.Thread(target=submit)
        thread.start()
        deadline = time.monotonic() + 1
        command = None
        while command is None and time.monotonic() < deadline:
            command = broker.next_command("review-session")
            if command is None:
                time.sleep(0.01)
        self.assertIsNotNone(command)
        broker.resolve(
            "review-session",
            command.id,
            BrowserResultRequest(status="completed", result={"tool": "observe_room", "views": []}),
        )
        thread.join(timeout=1)
        self.assertEqual(output[0].state, "completed")
        self.assertEqual(output[0].result["tool"], "observe_room")

    def test_session_mismatch_cannot_resolve_a_command(self) -> None:
        broker = RenderTaskBroker()
        request = AgentCommandRequest(tool="observe_home_harmony")
        command = None

        def submit() -> None:
            nonlocal command
            command = broker.submit("one", request)

        thread = threading.Thread(target=submit)
        thread.start()
        pending = None
        while pending is None:
            pending = broker.next_command("one")
        with self.assertRaises(KeyError):
            broker.resolve("other", pending.id, BrowserResultRequest(status="completed", result={}))
        broker.resolve("one", pending.id, BrowserResultRequest(status="failed", error="test"))
        thread.join(timeout=1)
        self.assertEqual(command.state, "failed")


if __name__ == "__main__":
    unittest.main()
