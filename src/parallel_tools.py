"""Parallel Search and Decisions tools for a LiveKit voice session."""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Literal

from livekit.agents import RunContext, ToolError, function_tool
from parallel import AsyncParallel

logger = logging.getLogger("agent.parallel")

SearchMode = Literal["turbo", "fast", "basic", "advanced"]


@dataclass
class ParallelConfig:
    api_key: str = field(default_factory=lambda: os.environ.get("PARALLEL_API_KEY", ""))
    search_mode: SearchMode = field(
        default_factory=lambda: os.environ.get("PARALLEL_SEARCH_MODE", "turbo")  # type: ignore[return-value]
    )
    # Keep tool output small: the LLM reads all of it before it can start talking.
    max_chars_total: int = field(
        default_factory=lambda: int(os.environ.get("PARALLEL_MAX_CHARS", "4000"))
    )
    max_results: int = field(
        default_factory=lambda: int(os.environ.get("PARALLEL_MAX_RESULTS", "5"))
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

    def as_tools(self) -> list:
        return [self.web_search, self.web_decisions]

    async def aclose(self) -> None:
        await self._client.close()

    # -- Tools ---------------------------------------------------------------

    @function_tool()
    async def web_search(
        self, context: RunContext, objective: str, search_queries: list[str]
    ) -> str:
        """Find sources for an open-ended question that needs external evidence.

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
    async def web_decisions(
        self, context: RunContext, entity: str, question: str
    ) -> str:
        """Check one yes/no claim against live web evidence.

        Args:
            entity: Public name and identifying context, such as an official domain.
            question: One verifiable yes/no question with any relevant date or criteria.
        """
        async with context.with_filler(
            _filler(context, ["Let me check that."]), delay=1.0
        ):
            try:
                return await self.decide(entity, question)
            except Exception as e:
                logger.exception("Parallel decision failed")
                raise ToolError("I couldn't verify that claim just now.") from e

    # -- Plain API calls (usable outside LiveKit, e.g. in tests) -------------

    async def search(self, objective: str, search_queries: list[str]) -> str:
        queries = [q.strip() for q in search_queries if q.strip()]
        if not queries:
            raise ValueError("Supply at least one keyword query.")
        res = await self._client.search(
            objective=objective,
            search_queries=queries[:3],
            mode=self.config.search_mode,
            max_chars_total=self.config.max_chars_total,
            session_id=self.session_id,
            client_model=self.config.client_model,
            advanced_settings={"max_results": self.config.max_results},
        )
        return _format_results(res.results) if res.results else "No results found."

    async def decide(self, entity: str, question: str) -> str:
        result = await self._client.post(
            "/v1/decisions",
            cast_to=object,
            body={
                "state": {"subject": entity},
                "questions": {"claim": {"type": "noul", "instructions": question}},
            },
        )
        answer = result["answers"]["claim"]
        if answer["type"] == "refusal":
            return (
                "No decision returned. Tell the caller the claim could not be verified."
            )
        lines = [f"Estimated probability the claim is true: {answer['noul']:.1%}"]
        for source in result["citations"][: self.config.max_results]:
            lines.append(f"{source.get('title') or 'Source'} ({source['url']})")
            for excerpt in source.get("excerpts", [])[:1]:
                lines.append(excerpt[:600])
        return "\n".join(lines)


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
