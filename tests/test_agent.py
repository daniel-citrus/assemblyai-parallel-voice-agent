"""Import-level checks that the agent wires up without any network calls."""

import os

# Dummy LiveKit credentials so inference.LLM() can be constructed offline.
for k, v in {"LIVEKIT_API_KEY": "test", "LIVEKIT_API_SECRET": "test"}.items():
    os.environ.setdefault(k, v)


def test_agent_builds():
    import agent

    a = agent.SearchAssistant(tools=[])
    assert "web_search" in a.instructions


def test_mcp_server_config():
    import agent

    assert agent.parallel_mcp_server() is not None
