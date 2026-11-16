"""A LiveKit voice agent that searches the live web with Parallel.

Pipeline: AssemblyAI Universal-3.5 Pro STT (via LiveKit Inference) -> LLM with
Parallel web tools -> AssemblyAI Streaming TTS.

Run it:
    uv run python src/agent.py download-files   # once, fetches turn-detector weights
    uv run python src/agent.py console          # talk to it in your terminal
    uv run python src/agent.py dev              # connect a frontend / Agent Console
"""

from __future__ import annotations

import logging
import os
import textwrap
from datetime import date

import assemblyai_tts
from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    STTContextOptions,
    TurnHandlingOptions,
    cli,
    inference,
    mcp,
    room_io,
)
from livekit.plugins import ai_coustics

from metrics import TurnMetricsReporter
from parallel_tools import ParallelTools

load_dotenv(".env.local")

logger = logging.getLogger("agent")
logger.setLevel(logging.INFO)

# "api" (default): direct Parallel Search / Extract / Responses tools from
#   parallel_tools.py. Lowest latency and fully tunable for voice.
# "mcp": the hosted Parallel MCP server (web_search, web_fetch). No tool code to
#   maintain; new Parallel tools show up automatically.
TOOL_SOURCE = os.environ.get("PARALLEL_TOOL_SOURCE", "api").lower()

# See all available models at https://docs.livekit.io/agents/models/llm/
LLM_MODEL = os.environ.get("LLM_MODEL", "google/gemma-4-31b-it")
TTS_VOICE = os.environ.get("ASSEMBLYAI_TTS_VOICE", "aai-violet")

INSTRUCTIONS = textwrap.dedent(
    """\
    You are a friendly voice assistant that can search the live web. Today is
    {today}.

    How you speak:
    - Plain text only; everything you say is read aloud. No markdown, lists,
      URLs or emoji.
    - Keep replies to one to three short sentences. Ask one question at a time.
    - Spell out numbers, dates, phone numbers and email addresses naturally.

    How you use the web:
    - For anything current, factual or uncertain, call web_search before you
      answer. Don't guess, and don't say you lack internet access.
    - Write a clear objective and 1-3 short keyword queries that include the
      key entity and, when it matters, the date or year.
    - Use read_webpage only when a search result looks right but lacks detail,
      or the caller gives you a link.
    - Use deep_research only for comparisons or multi-step questions that one
      search can't answer.
    - Don't announce that you're searching; the system plays a short filler
      if a search takes a moment.
    - Answer from the results, mention the source by name when it helps
      ("according to Reuters"), and say so plainly if the results don't answer
      the question.
    """
)


class SearchAssistant(Agent):
    def __init__(self, tools: list | None = None) -> None:
        super().__init__(
            llm=inference.LLM(model=LLM_MODEL),
            instructions=INSTRUCTIONS.format(
                today=date.today().strftime("%A, %B %d, %Y")
            ),
            tools=tools or [],
        )

    async def on_enter(self) -> None:
        self.session.generate_reply(
            instructions="Greet the caller in one short sentence and offer to look "
            "anything up on the web for them."
        )


def parallel_mcp_server() -> mcp.MCPServerHTTP:
    """The hosted Parallel MCP server. Works without a key (rate limited);
    with PARALLEL_API_KEY set, calls are billed to your account at higher limits."""
    key = os.environ.get("PARALLEL_API_KEY")
    return mcp.MCPServerHTTP(
        url="https://mcp.parallel.ai/mcp",
        transport_type="streamable_http",
        headers={"Authorization": f"Bearer {key}"} if key else None,
        allowed_tools=["web_search", "web_fetch"],
        timeout=15,
        client_session_timeout_seconds=30,
    )


server = AgentServer()


@server.rtc_session(agent_name="parallel-search-agent")
async def entrypoint(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name}

    tools: list = []
    session_kwargs: dict = {}
    if TOOL_SOURCE == "mcp":
        session_kwargs["mcp_servers"] = [parallel_mcp_server()]
    else:
        parallel = ParallelTools(session_id=ctx.room.name)
        tools = parallel.as_tools()
        ctx.add_shutdown_callback(parallel.aclose)
    logger.info("Parallel tools via %s", TOOL_SOURCE)

    session = AgentSession(
        **session_kwargs,
        # Speech-to-text via LiveKit Inference (AssemblyAI Universal-3.5 Pro).
        # See https://docs.livekit.io/agents/models/stt/
        stt=inference.STT(model="assemblyai/universal-3-5-pro", language="en"),
        # Keyterms boost recognition of names callers are likely to search for.
        stt_context_options=STTContextOptions(
            keyterms=["Parallel", "LiveKit", "AssemblyAI"],
            keyterm_detection={"enabled": True},
        ),
        # AssemblyAI Streaming TTS. Reads ASSEMBLYAI_API_KEY from the environment.
        tts=assemblyai_tts.TTS(voice_id=TTS_VOICE, language="english"),
        turn_handling=TurnHandlingOptions(
            turn_detection=inference.TurnDetector(),
            interruption={"mode": "adaptive"},
            preemptive_generation={"enabled": True},
        ),
        # The AssemblyAI TTS plugin doesn't render expressive markup; keep it off
        # so tags never leak into speech.
        expressive=False,
    )

    TurnMetricsReporter().attach(session)

    await session.start(
        agent=SearchAssistant(tools=tools),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=ai_coustics.audio_enhancement(
                    model=ai_coustics.EnhancerModel.QUAIL_VF_S
                ),
            ),
        ),
    )

    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(server)
