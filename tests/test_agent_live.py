"""End-to-end text tests: real LLM (AssemblyAI LLM Gateway) + real Parallel search.

No audio and no LiveKit server: AgentSession runs in text mode. Skipped unless
ASSEMBLYAI_API_KEY and PARALLEL_API_KEY are both set.
"""

import os
from datetime import date

import pytest
from dotenv import load_dotenv
from livekit.agents import AgentSession

load_dotenv(".env.local")

pytestmark = pytest.mark.skipif(
    not (os.environ.get("ASSEMBLYAI_API_KEY") and os.environ.get("PARALLEL_API_KEY")),
    reason="needs ASSEMBLYAI_API_KEY and PARALLEL_API_KEY",
)


async def _run(user_input: str):
    os.environ.setdefault("AGENT_STACK", "local")
    from livekit.plugins import openai

    import agent
    from parallel_tools import ParallelTools

    tools = ParallelTools(session_id="pytest")
    # The judge sends `temperature`, which some gateway models (e.g. Claude Haiku
    # 5.5) reject, so it uses its own model.
    judge = openai.LLM(
        model=os.environ.get("JUDGE_MODEL", agent.LLM_MODEL),
        base_url=agent.LLM_GATEWAY_URL,
        api_key=os.environ["ASSEMBLYAI_API_KEY"],
    )
    try:
        async with AgentSession(llm=agent.build_llm()) as session:
            await session.start(agent.SearchAssistant(tools=tools.as_tools()))
            result = await session.run(user_input=user_input)
            return result, judge
    finally:
        await tools.aclose()


async def test_searches_for_current_info():
    result, judge = await _run("What's the latest version of the LiveKit Agents SDK?")
    result.expect.contains_function_call(name="web_search")
    await result.expect.contains_message(role="assistant").judge(
        judge,
        intent=f"Today is {date.today():%B %d, %Y}. Names a specific LiveKit "
        "Agents version number taken from the search results, in plain spoken "
        "text with no markdown or URLs.",
    )


async def test_no_search_for_small_talk():
    result, judge = await _run("Hi there, how are you?")
    for tool_name in ("web_search", "web_decisions"):
        with pytest.raises(AssertionError):
            result.expect.contains_function_call(name=tool_name)
    await result.expect.contains_message(role="assistant").judge(
        judge, intent="A short, friendly reply."
    )


async def test_checks_a_public_claim():
    result, _ = await _run("Does Python 3.13 offer a free-threaded build?")
    result.expect.contains_function_call(name="web_decisions")
    result.expect.contains_message(role="assistant")
