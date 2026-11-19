"""Import-level checks that the agent wires up without any network calls."""


def test_agent_builds(monkeypatch):
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "test")
    import agent
    from page_images import page_images

    a = agent.SearchAssistant()
    assert "web_search" in a.instructions
    assert "page_images" in a.instructions
    assert page_images in a.tools
