"""LangSmith tracing stays project-scoped and carries evaluation dimensions."""

import unittest
from unittest.mock import patch

from backend.agent_api.config import settings
from backend.agent_api.telemetry import (
    build_graph_config,
    langsmith_tool_span,
    langsmith_tracing_scope,
)


class _Context:
    def __init__(self, value=None):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, traceback):
        return False


class LangSmithTelemetryTests(unittest.TestCase):
    def test_graph_config_contains_trace_dimensions_without_secrets(self) -> None:
        config = build_graph_config(
            thread_id="thread-1",
            design_run_id="run-1",
            design_mode="fresh",
            transport="json",
        )

        self.assertEqual(config["run_name"], "house-design-agent-turn")
        self.assertEqual(config["configurable"]["thread_id"], "thread-1")
        self.assertEqual(config["metadata"]["design_run_id"], "run-1")
        self.assertEqual(config["metadata"]["design_mode"], "fresh")
        self.assertEqual(config["metadata"]["transport"], "json")
        self.assertNotIn("api_key", str(config).lower())

    def test_disabled_scope_explicitly_overrides_generic_environment(self) -> None:
        with (
            patch.object(settings, "langsmith_tracing", False),
            patch(
                "backend.agent_api.telemetry.get_langsmith_client",
                return_value=None,
            ),
            patch(
                "backend.agent_api.telemetry.ls.tracing_context",
                return_value=_Context(),
            ) as tracing_context,
        ):
            with langsmith_tracing_scope(
                thread_id="thread-2",
                design_run_id=None,
                design_mode="continue",
                transport="sse",
            ):
                pass

        self.assertFalse(tracing_context.call_args.kwargs["enabled"])
        self.assertIsNone(tracing_context.call_args.kwargs["client"])

    def test_enabled_tool_span_uses_dynamic_tool_name_and_explicit_client(self) -> None:
        fake_client = object()
        fake_run = object()
        with (
            patch.object(settings, "langsmith_tracing", True),
            patch(
                "backend.agent_api.telemetry.get_langsmith_client",
                return_value=fake_client,
            ),
            patch(
                "backend.agent_api.telemetry.ls.trace",
                return_value=_Context(fake_run),
            ) as trace,
        ):
            with langsmith_tool_span("update_scheme", {"target_id": "wall-1"}) as run:
                self.assertIs(run, fake_run)

        kwargs = trace.call_args.kwargs
        self.assertEqual(kwargs["name"], "house-design-tool:update_scheme")
        self.assertEqual(kwargs["run_type"], "tool")
        self.assertIs(kwargs["client"], fake_client)

    def test_tool_span_records_tool_call_id_in_metadata(self) -> None:
        fake_client = object()
        fake_run = object()
        with (
            patch.object(settings, "langsmith_tracing", True),
            patch(
                "backend.agent_api.telemetry.get_langsmith_client",
                return_value=fake_client,
            ),
            patch(
                "backend.agent_api.telemetry.ls.trace",
                return_value=_Context(fake_run),
            ) as trace,
        ):
            with langsmith_tool_span(
                "observe_room", {"room_id": "open_public"}, "call-123"
            ) as run:
                self.assertIs(run, fake_run)

        metadata = trace.call_args.kwargs["metadata"]
        self.assertEqual(metadata["tool_name"], "observe_room")
        self.assertEqual(metadata["tool_call_id"], "call-123")

    def test_tool_span_omits_tool_call_id_when_absent(self) -> None:
        fake_client = object()
        fake_run = object()
        with (
            patch.object(settings, "langsmith_tracing", True),
            patch(
                "backend.agent_api.telemetry.get_langsmith_client",
                return_value=fake_client,
            ),
            patch(
                "backend.agent_api.telemetry.ls.trace",
                return_value=_Context(fake_run),
            ) as trace,
        ):
            with langsmith_tool_span("load_scheme", {}) as run:
                self.assertIs(run, fake_run)

        metadata = trace.call_args.kwargs["metadata"]
        self.assertEqual(metadata["tool_name"], "load_scheme")
        self.assertNotIn("tool_call_id", metadata)


if __name__ == "__main__":
    unittest.main()
