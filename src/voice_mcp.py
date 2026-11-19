"""Acknowledge slow web lookups while keeping Parallel's hosted tool schemas."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from livekit.agents import RunContext, function_tool, mcp

# What the agent says when a lookup takes more than a second. web/index.html
# tells these from real replies because each starts with "One sec".
ACKNOWLEDGMENTS = {
    "web_search": "One sec, I'm searching the web.",
    "web_fetch": "One sec, I'm reading the page.",
    "web_decisions": "One sec, I'm weighing the evidence.",
    "page_images": "One sec, I'm reading about the page's pictures.",
}
DEFAULT_ACKNOWLEDGMENT = "One sec, let me check."


@asynccontextmanager
async def acknowledge_slow_lookup(
    ctx: RunContext, tool_name: str
) -> AsyncIterator[None]:
    phrase = ACKNOWLEDGMENTS.get(tool_name, DEFAULT_ACKNOWLEDGMENT)

    def acknowledge(step: int):
        return ctx.session.say(phrase, add_to_chat_ctx=False, allow_interruptions=True)

    async with ctx.with_filler(acknowledge, delay=1.0):
        yield


def with_spoken_acknowledgment(tool: mcp.MCPTool) -> mcp.MCPTool:
    @function_tool(raw_schema=tool.info.raw_schema)
    async def call(ctx: RunContext, raw_arguments: dict[str, Any]) -> Any:
        async with acknowledge_slow_lookup(ctx, tool.info.name):
            return await tool(raw_arguments)

    return call


class VoiceMCPServer(mcp.MCPServerHTTP):
    async def list_tools(self, *, tool_options=None):
        tools = await super().list_tools(tool_options=tool_options)
        return [with_spoken_acknowledgment(tool) for tool in tools]
