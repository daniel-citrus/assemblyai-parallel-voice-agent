# Helping someone run this starter

This is a voice assistant for blind and low-vision callers. It searches the web with Parallel and describes a page's pictures from the page's alt text, captions and nearby text, never from the image itself.

Use the terminal quickstart in [README.md](README.md#run-it). If you are already in the checkout, start at `uv sync --frozen`. Run from the repo root so the app finds `.env.local`.

- Use existing environment variables or an existing `.env.local`. Only the AssemblyAI key is required for the voice demo. Have the developer set it locally if missing. Preserve existing settings and keep key values out of chat and logs.
- In an interactive terminal, use the README examples to exercise Search, Fetch, Decisions, and picture descriptions, such as “Describe the main photo on the Wikipedia article about the Golden Gate Bridge.” The greeting is fixed and can play even when the gateway rejects the first question.
- In a headless shell with an AssemblyAI key configured, run `uv run pytest -q tests/test_agent_live.py` to check routing through the live APIs, including one picture description. Skipped tests mean the integration is unverified. This check uses text. Have the developer try their microphone and speakers locally.
- A thin picture description usually means the page has no alt text or captions, not that the tool failed. The agent should say what its description is based on and never claim to see an image.
- If a turn fails, follow [troubleshooting](docs/advanced.md#troubleshooting) to isolate audio, AssemblyAI gateway access, Parallel, or `page_images`. The terminal demo needs neither a separate LiveKit server nor cloud credentials.
