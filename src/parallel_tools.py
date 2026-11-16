"""Parallel web tools for LiveKit voice agents.

Three tools, ordered by latency, so the LLM can pick the cheapest one that answers
the question:

* ``web_search``    - Parallel Search API (``fast`` mode, ~700 ms). Default tool.
* ``read_webpage``  - Parallel Extract API. Read one page the caller names or that
                      a search surfaced.
* ``deep_research`` - Parallel Responses API (``low`` effort, ~5-10 s). A cited,
                      synthesized answer for multi-hop questions.

Voice-specific choices (all overridable with environment variables):

* Results are trimmed hard (``max_chars_total``) because every token the LLM reads
  adds to time-to-first-word.
* A spoken filler ("One sec, let me look that up.") plays only if a tool runs long
  enough for the silence to be noticeable, using ``RunContext.with_filler``.
* One ``session_id`` per call (LiveKit room) groups Search and Extract calls, as
  Parallel recommends.

Docs: https://docs.parallel.ai/search/best-practices
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Literal

from livekit.agents import RunContext, ToolError, function_tool
from openai import AsyncOpenAI
from parallel import AsyncParallel

logger = logging.getLogger("agent.parallel")

SearchMode = Literal["turbo", "fast", "basic", "advanced"]


@dataclass
class ParallelConfig:
    api_key: str = field(default_factory=lambda: os.environ.get("PARALLEL_API_KEY", ""))
    # turbo ~200 ms (English/Japanese only) | fast ~700 ms | basic ~1 s | advanced ~3 s
    search_mode: SearchMode = field(
        default_factory=lambda: os.environ.get("PARALLEL_SEARCH_MODE", "fast")  # type: ignore[return-value]
    )
    # Keep tool output small: the LLM reads all of it before it can start talking.
    max_chars_total: int = field(
        default_factory=lambda: int(os.environ.get("PARALLEL_MAX_CHARS", "4000"))
    )
    max_results: int = field(
        default_factory=lambda: int(os.environ.get("PARALLEL_MAX_RESULTS", "5"))
    )
    # low ~5-10 s | medium ~15-20 s | high ~30-60 s
    research_effort: str = field(
        default_factory=lambda: os.environ.get("PARALLEL_RESEARCH_EFFORT", "low")
    )
    # Tells Parallel which model reads the results so it can tune excerpts.
    client_model: str | None = None


class ParallelTools:
    """Holds the Parallel clients for one call and exposes them as LiveKit tools.

    Usage::

        tools = ParallelTools(session_id=ctx.room.name)
        Agent(instructions=..., tools=tools.as_tools())
    """

    def __init__(
        self, config: ParallelConfig | None = None, *, session_id: str | None = None
    ) -> None:
        self.config = config or ParallelConfig()
        if not self.config.api_key:
            raise RuntimeError(
                "PARALLEL_API_KEY is not set. Get one at https://platform.parallel.ai"
            )
        self.session_id = f"voice_{session_id or uuid.uuid4().hex}"
        self._client = AsyncParallel(api_key=self.config.api_key)
        # The Responses API is OpenAI-compatible, so the OpenAI SDK talks to it.
        self._responses = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url="https://api.parallel.ai/v1",
            timeout=90.0,
        )

    def as_tools(self) -> list:
        return [self.web_search, self.read_webpage, self.deep_research]

    async def aclose(self) -> None:
        await self._client.close()
        await self._responses.close()

    # -- Tools ---------------------------------------------------------------

    @function_tool()
    async def web_search(
        self, context: RunContext, objective: str, search_queries: list[str]
    ) -> str:
        """Search the live web. Use for anything current, factual, or that you are
        not sure about: news, prices, scores, weather, people, companies, products,
        schedules, and anything after your training cutoff.

        Args:
            objective: The search goal as one standalone sentence. Name the key
                entity or topic and any freshness requirement, e.g. "Find today's
                weather forecast for Austin, Texas."
            search_queries: 1-3 keyword queries of 3-6 words each. Include the key
                entity in every query and vary the angle. No full sentences and no
                site: operators.
        """
        logger.info("web_search objective=%r queries=%r", objective, search_queries)
        async with context.with_filler(
            _filler(context, ["One sec, let me look that up."]), delay=1.0
        ):
            try:
                return await self.search(objective, search_queries)
            except Exception as e:
                logger.exception("Parallel search failed")
                raise ToolError("The web search failed. Try again shortly.") from e

    @function_tool()
    async def read_webpage(self, context: RunContext, url: str, objective: str) -> str:
        """Read a specific web page and pull out what is relevant. Use when the
        caller names a URL, or when a search result looks right but its excerpt
        lacks the detail you need.

        Args:
            url: The full URL of the page, starting with https://.
            objective: What you need from the page, as one sentence.
        """
        logger.info("read_webpage url=%r objective=%r", url, objective)
        async with context.with_filler(
            _filler(context, ["Let me pull up that page."]), delay=1.0
        ):
            try:
                return await self.extract(url, objective)
            except Exception as e:
                logger.exception("Parallel extract failed")
                raise ToolError("I couldn't open that page.") from e

    @function_tool()
    async def deep_research(self, context: RunContext, question: str) -> str:
        """Research a question that needs several searches and reasoning across
        sources, such as comparisons, "which is the best", or multi-step questions.
        Takes 5-10 seconds, so prefer web_search for simple lookups.

        Args:
            question: The complete question, standalone, with all the context
                needed to answer it.
        """
        logger.info("deep_research question=%r", question)
        async with context.with_filler(
            _filler(context, _RESEARCH_FILLERS), delay=0.5, interval=6.0
        ):
            try:
                return await self.research(question)
            except Exception as e:
                logger.exception("Parallel research failed")
                raise ToolError("The research request failed.") from e

    # -- Plain API calls (usable outside LiveKit, e.g. in tests) -------------

    async def search(self, objective: str, search_queries: list[str]) -> str:
        res = await self._client.search(
            objective=objective,
            search_queries=search_queries[:3] or [objective],
            mode=self.config.search_mode,
            max_chars_total=self.config.max_chars_total,
            session_id=self.session_id,
            client_model=self.config.client_model,
            advanced_settings={"max_results": self.config.max_results},
        )
        return _format_results(res.results) if res.results else "No results found."

    async def extract(self, url: str, objective: str) -> str:
        res = await self._client.extract(
            urls=[url],
            objective=objective,
            max_chars_total=self.config.max_chars_total,
            session_id=self.session_id,
            client_model=self.config.client_model,
        )
        if not res.results:
            return "The page could not be read."
        return _format_results(res.results)

    async def research(self, question: str) -> str:
        r = await self._responses.responses.create(
            model="parallel",
            input=question,
            reasoning={"effort": self.config.research_effort},
            instructions=(
                "The answer will be read aloud by a voice assistant. "
                "Answer in at most five short sentences of plain text."
            ),
        )
        return r.output_text or "No answer found."


_RESEARCH_FILLERS = [
    "Let me dig into that, it'll take a few seconds.",
    "Still checking a few sources.",
    "Almost there.",
]


def _filler(context: RunContext, lines: list[str]):
    """Filler source for ``RunContext.with_filler`` that speaks ``lines`` in order.

    Fillers are spoken but kept out of the chat history. Otherwise the history
    would end on an assistant message right after the tool call, which some
    models (e.g. Claude via the LLM Gateway) reject as "assistant prefill".
    """

    def source(step: int):
        if step >= len(lines):
            return None
        return context.session.say(
            lines[step], add_to_chat_ctx=False, allow_interruptions=True
        )

    return source


def _format_results(results) -> str:
    """Compact, LLM-friendly text: title, URL, date, then excerpts."""
    blocks = []
    for i, r in enumerate(results, 1):
        head = f"[{i}] {r.title or 'Untitled'} ({r.url})"
        if getattr(r, "publish_date", None):
            head += f" published {r.publish_date}"
        excerpts = "\n".join(r.excerpts or [])
        blocks.append(f"{head}\n{excerpts}".strip())
    return "\n\n".join(blocks)
