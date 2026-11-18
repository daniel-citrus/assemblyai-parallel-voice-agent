"""Send tool calls and errors to the room so the web test page can show them.

The page in web/index.html listens on TOPIC. Speech transcripts already reach it
through LiveKit's built-in lk.transcription stream, so only tool activity and
errors are sent here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from livekit import rtc
from livekit.agents import (
    AgentSession,
    ErrorEvent,
    FunctionToolsExecutedEvent,
    ToolExecutionUpdatedEvent,
)

logger = logging.getLogger("agent.web")

TOPIC = "parallel.events"
# Data packets have a size limit, and the page only needs a preview of each result.
MAX_OUTPUT_CHARS = 2000


class ToolEventPublisher:
    def __init__(self, room: rtc.Room) -> None:
        self._room = room
        self._started: dict[str, float] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def attach(self, session: AgentSession) -> None:
        session.on("tool_execution_updated", self._on_tool_execution_updated)
        session.on("function_tools_executed", self._on_function_tools_executed)
        session.on("error", self._on_error)

    def _on_tool_execution_updated(self, ev: ToolExecutionUpdatedEvent) -> None:
        if ev.update.type != "tool_call_started":
            return
        call = ev.update.function_call
        self._started[call.call_id] = time.monotonic()
        self._send(
            {
                "type": "tool_started",
                "id": call.call_id,
                "name": call.name,
                "arguments": _parse_arguments(call.arguments),
            }
        )

    def _on_function_tools_executed(self, ev: FunctionToolsExecutedEvent) -> None:
        for call, output in ev.zipped():
            started = self._started.pop(call.call_id, None)
            self._send(
                {
                    "type": "tool_ended",
                    "id": call.call_id,
                    "name": call.name,
                    "arguments": _parse_arguments(call.arguments),
                    "is_error": output.is_error,
                    "output": output.output[:MAX_OUTPUT_CHARS],
                    "truncated": len(output.output) > MAX_OUTPUT_CHARS,
                    "seconds": None
                    if started is None
                    else round(time.monotonic() - started, 2),
                }
            )

    def _on_error(self, ev: ErrorEvent) -> None:
        # Plugin errors wrap the underlying exception, which has the useful message.
        error = getattr(ev.error, "error", ev.error)
        self._send(
            {
                "type": "error",
                "source": type(ev.source).__name__,
                "message": f"{type(error).__name__}: {error}",
                "recoverable": getattr(ev.error, "recoverable", False),
            }
        )

    def _send(self, event: dict[str, Any]) -> None:
        if not self._room.isconnected():
            return
        task = asyncio.create_task(self._publish(event))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _publish(self, event: dict[str, Any]) -> None:
        try:
            await self._room.local_participant.publish_data(
                json.dumps(event), reliable=True, topic=TOPIC
            )
        except Exception:
            logger.warning("could not send %s to the web page", event["type"])


def _parse_arguments(arguments: str) -> Any:
    try:
        return json.loads(arguments)
    except ValueError:
        return arguments
