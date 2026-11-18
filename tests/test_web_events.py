import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from livekit.agents import (
    ErrorEvent,
    FunctionToolsExecutedEvent,
    ToolCallStarted,
    ToolExecutionUpdatedEvent,
    llm,
)

from web_events import MAX_OUTPUT_CHARS, TOPIC, ToolEventPublisher


def make_publisher(connected=True):
    room = Mock(isconnected=Mock(return_value=connected))
    room.local_participant.publish_data = AsyncMock()
    return ToolEventPublisher(room), room.local_participant.publish_data


async def sent_events(publish):
    await asyncio.sleep(0)
    for call in publish.await_args_list:
        assert call.kwargs == {"reliable": True, "topic": TOPIC}
    return [json.loads(call.args[0]) for call in publish.await_args_list]


async def test_tool_call_is_sent_when_it_starts_and_ends():
    publisher, publish = make_publisher()
    call = llm.FunctionCall(
        call_id="call_1", name="web_search", arguments='{"objective": "Python"}'
    )
    output = llm.FunctionCallOutput(
        call_id="call_1",
        name="web_search",
        output="x" * (MAX_OUTPUT_CHARS + 1),
        is_error=False,
    )

    publisher._on_tool_execution_updated(
        ToolExecutionUpdatedEvent(update=ToolCallStarted(function_call=call))
    )
    publisher._on_function_tools_executed(
        FunctionToolsExecutedEvent(
            function_calls=[call], function_call_outputs=[output]
        )
    )

    started, ended = await sent_events(publish)
    assert started == {
        "type": "tool_started",
        "id": "call_1",
        "name": "web_search",
        "arguments": {"objective": "Python"},
    }
    assert ended["type"] == "tool_ended"
    assert ended["arguments"] == {"objective": "Python"}
    assert len(ended["output"]) == MAX_OUTPUT_CHARS
    assert ended["truncated"] is True
    assert ended["is_error"] is False
    assert isinstance(ended["seconds"], float)


async def test_error_names_the_underlying_exception():
    publisher, publish = make_publisher()
    publisher._on_error(
        ErrorEvent(
            error=SimpleNamespace(error=ValueError("model not enabled")), source=None
        )
    )

    (event,) = await sent_events(publish)
    assert event["message"] == "ValueError: model not enabled"
    assert event["recoverable"] is False


async def test_nothing_is_sent_outside_a_connected_room():
    publisher, publish = make_publisher(connected=False)
    publisher._on_error(ErrorEvent(error=RuntimeError("boom"), source=None))

    assert await sent_events(publish) == []
