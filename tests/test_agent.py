"""Import-level checks that the agent wires up without any network calls."""


def test_agent_builds(monkeypatch):
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "test")
    import agent
    from page_images import page_images

    a = agent.SearchAssistant()
    assert "web_search" in a.instructions
    assert "page_images" in a.instructions
    assert page_images in a.tools


def test_session_retries_a_stalled_llm_request_after_five_seconds():
    import agent

    options = agent.CONN_OPTIONS.llm_conn_options
    assert options.timeout == 5
    assert options.max_retry == 3
