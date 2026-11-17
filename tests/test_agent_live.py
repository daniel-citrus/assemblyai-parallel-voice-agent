"""Live text turns through AssemblyAI and the hosted Parallel MCP server."""

import os

import pytest
from dotenv import load_dotenv
from livekit.agents import AgentSession

load_dotenv(".env.local")

pytestmark = pytest.mark.skipif(
    not os.environ.get("ASSEMBLYAI_API_KEY"),
    reason="needs ASSEMBLYAI_API_KEY",
)


async def _run(user_input: str):
    import agent

    async with AgentSession() as session:
        await session.start(agent.SearchAssistant())
        return await session.run(user_input=user_input)


async def test_searches_for_current_info():
    result = await _run("What's the latest version of the LiveKit Agents SDK?")
    result.expect.contains_function_call(name="web_search")
    result.expect.contains_function_call_output(is_error=False)
    message = result.expect.contains_message(role="assistant").event().item.text_content
    assert message and "http" not in message and "```" not in message


async def test_no_search_for_small_talk():
    result = await _run("Hi there, how are you?")
    for tool_name in ("web_search", "web_fetch", "web_decisions"):
        with pytest.raises(AssertionError):
            result.expect.contains_function_call(name=tool_name)
    assert result.expect.contains_message(role="assistant").event().item.text_content


async def test_checks_a_public_claim():
    result = await _run("Does Python 3.13 offer a free-threaded build?")
    result.expect.contains_function_call(name="web_decisions")
    result.expect.contains_function_call_output(is_error=False)
    result.expect.contains_message(role="assistant")


async def test_fetches_a_specific_page():
    result = await _run(
        "Read https://docs.python.org/3/howto/free-threading-python.html "
        "and tell me what the page says about checking whether the GIL is enabled."
    )
    result.expect.contains_function_call(name="web_fetch")
    result.expect.contains_function_call_output(is_error=False)
    result.expect.contains_message(role="assistant")
