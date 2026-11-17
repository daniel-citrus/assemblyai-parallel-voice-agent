"""Import-level checks that the agent wires up without any network calls."""


def test_agent_builds(monkeypatch):
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "test")
    import agent

    a = agent.SearchAssistant(tools=[])
    assert "web_search" in a.instructions


def test_mcp_server_config():
    import agent

    assert agent.parallel_mcp_server() is not None
