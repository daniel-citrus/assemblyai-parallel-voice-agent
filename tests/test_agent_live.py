"""End-to-end text tests: real LLM (AssemblyAI LLM Gateway) + real Parallel search.

No audio and no LiveKit server: AgentSession runs in text mode. Skipped unless
ASSEMBLYAI_API_KEY and PARALLEL_API_KEY are both set.
"""

import os

import pytest
from dotenv import load_dotenv
from livekit.agents import AgentSession

load_dotenv(".env.local")

pytestmark = pytest.mark.skipif(
    not (os.environ.get("ASSEMBLYAI_API_KEY") and os.environ.get("PARALLEL_API_KEY")),
    reason="needs ASSEMBLYAI_API_KEY and PARALLEL_API_KEY",
)


async def _run(user_input: str):
    import agent
    from parallel_tools import ParallelTools

    tools = ParallelTools(session_id="pytest")
    try:
        async with AgentSession(llm=agent.build_llm()) as session:
            await session.start(agent.SearchAssistant(tools=tools.as_tools()))
            result = await session.run(user_input=user_input)
            return result
    finally:
        await tools.aclose()


async def test_searches_for_current_info():
    result = await _run("What's the latest version of the LiveKit Agents SDK?")
    result.expect.contains_function_call(name="web_search")
    message = result.expect.contains_message(role="assistant").event().item.text_content
    assert message and "http" not in message and "```" not in message


async def test_no_search_for_small_talk():
    result = await _run("Hi there, how are you?")
    for tool_name in ("web_search", "web_decisions"):
        with pytest.raises(AssertionError):
            result.expect.contains_function_call(name=tool_name)
    assert result.expect.contains_message(role="assistant").event().item.text_content


async def test_checks_a_public_claim():
    result = await _run("Does Python 3.13 offer a free-threaded build?")
    result.expect.contains_function_call(name="web_decisions")
    result.expect.contains_message(role="assistant")
