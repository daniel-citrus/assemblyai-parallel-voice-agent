# AssemblyAI + Parallel voice starter

Talk to a voice agent in your terminal. AssemblyAI listens and speaks. The agent uses Parallel **Search** to find sources and **Decisions** to check a yes/no claim. You can run it locally with two API keys and no LiveKit account.

## Run it

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then open a terminal:

```sh
git clone https://github.com/hsingh-aai/assemblyai-parallel-voice-agent.git
cd assemblyai-parallel-voice-agent
uv sync --frozen
```

Copy `.env.example` to `.env.local`. Fill in `ASSEMBLYAI_API_KEY` and `PARALLEL_API_KEY` with keys from [AssemblyAI](https://www.assemblyai.com/dashboard) and [Parallel](https://platform.parallel.ai).

```sh
uv run python src/agent.py console --log-level info
```

Allow microphone access and wait for the greeting. To type instead, add `--text` to the command. Press Ctrl+C to quit.

## Try two questions

1. **“What changed in the latest stable Python release?”** Look for `Search` and a source URL in the terminal.
2. **“Does that version offer a free-threaded build?”** In the same conversation, the agent can use `Decisions` to check the release it just named. Look for a probability and a source, or a message that it couldn't verify the claim.

## Make it yours

Try a library compatibility assistant. Set `AGENT_GREETING="Which library are you working with?"` in `.env.local`. Add “Prefer official release notes and package metadata” to `INSTRUCTIONS` in [src/agent.py](src/agent.py). Restart and try the same two questions about a library you use.

Building a different app? [parallel_api.py](src/parallel_api.py) has the two API calls and only needs `parallel-web`. [try_parallel.py](scripts/try_parallel.py) shows how to use them.

[Setup help](docs/advanced.md#troubleshooting) · [Browser and deployment options](docs/advanced.md#browser-or-room)
