# Helping someone run this starter

Use the terminal quickstart in [README.md](README.md#run-it). If you are already in the checkout, start at `uv sync --frozen`. Run from the repo root so the app finds `.env.local`.

- Use existing environment variables or an existing `.env.local`. If keys are missing, have the developer fill in the missing values locally. Preserve existing settings and keep key values out of chat and logs.
- In an interactive terminal, use the README's two questions to verify Search and Decisions. The greeting is fixed and can play even when the gateway rejects the first question.
- In a headless shell with both keys configured, run `uv run pytest -q tests/test_agent_live.py` to check routing through the live APIs. Skipped tests mean the integration is unverified. This check uses text. Have the developer try their microphone and speakers locally.
- If a turn fails, follow [troubleshooting](docs/advanced.md#troubleshooting) to isolate audio, AssemblyAI gateway access, or Parallel. The terminal demo needs neither a separate LiveKit server nor cloud credentials.
