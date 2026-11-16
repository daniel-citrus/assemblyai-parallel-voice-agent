import os
from types import SimpleNamespace

import pytest

from parallel_tools import ParallelConfig, ParallelTools, _format_results


def test_format_results():
    results = [
        SimpleNamespace(
            title="Hello",
            url="https://a.com",
            publish_date="2026-01-02",
            excerpts=["one", "two"],
        ),
        SimpleNamespace(
            title=None, url="https://b.com", publish_date=None, excerpts=[]
        ),
    ]
    out = _format_results(results)
    assert "[1] Hello (https://a.com) published 2026-01-02\none\ntwo" in out
    assert "[2] Untitled (https://b.com)" in out


def test_tools_register():
    tools = ParallelTools(ParallelConfig(api_key="test"), session_id="room")
    names = [t.id for t in tools.as_tools()]
    assert names == ["web_search", "read_webpage", "deep_research"]
    assert tools.session_id == "voice_room"


def test_missing_key_raises():
    with pytest.raises(RuntimeError):
        ParallelTools(ParallelConfig(api_key=""))


live = pytest.mark.skipif(
    not os.environ.get("PARALLEL_API_KEY"), reason="PARALLEL_API_KEY not set"
)


@live
async def test_live_search():
    tools = ParallelTools()
    try:
        out = await tools.search(
            "Find the official website of the LiveKit Agents framework.",
            ["LiveKit Agents framework", "LiveKit voice agents"],
        )
    finally:
        await tools.aclose()
    assert "livekit" in out.lower()
