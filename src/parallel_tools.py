"""Parallel Search and Decisions tools for a LiveKit voice session."""

from __future__ import annotations

import logging

from livekit.agents import RunContext, ToolError, function_tool

from parallel_api import ParallelAPI

logger = logging.getLogger("agent.parallel")


class ParallelTools(ParallelAPI):
    def as_tools(self) -> list:
        return [self.web_search, self.web_decisions]

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
