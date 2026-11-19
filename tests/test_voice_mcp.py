import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from livekit.agents import RunContext, function_tool

from voice_mcp import with_spoken_acknowledgment


async def run_lookup(name, slow):
    """Run a wrapped tool and return the session that would speak for it."""
    spoken = asyncio.Event()
    session = Mock(wait_for_idle=AsyncMock())
    session.say.side_effect = lambda *args, **kwargs: spoken.set()

    async def wait_for_tasks(tasks):
        await asyncio.gather(*tasks)

    ctx = RunContext(
        session=session,
        speech_handle=SimpleNamespace(
            num_steps=1, wait_if_not_interrupted=wait_for_tasks
        ),
        function_call=Mock(),
    )
    schema = {"name": name, "parameters": {"type": "object"}}

    @function_tool(raw_schema=schema)
    async def lookup(raw_arguments):
        if slow:
            await asyncio.wait_for(spoken.wait(), timeout=4)
        return raw_arguments

    tool = with_spoken_acknowledgment(lookup)
    assert tool.info.raw_schema == lookup.info.raw_schema
    assert await tool(ctx, {"query": "Python"}) == {"query": "Python"}
    return session


@pytest.mark.parametrize(
    "name, phrase",
    [
        ("web_search", "One sec, I'm searching the web."),
        ("web_fetch", "One sec, I'm reading the page."),
        ("web_decisions", "One sec, I'm weighing the evidence."),
        ("page_images", "One sec, I'm reading about the page's pictures."),
        ("some_new_tool", "One sec, let me check."),
    ],
)
async def test_slow_lookup_says_what_it_is_doing(name, phrase):
    session = await run_lookup(name, slow=True)

    session.say.assert_called_once_with(
        phrase, add_to_chat_ctx=False, allow_interruptions=True
    )


async def test_fast_lookup_says_nothing():
    session = await run_lookup("web_search", slow=False)

    session.say.assert_not_called()
