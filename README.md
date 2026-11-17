# Build a voice agent with AssemblyAI and Parallel

Ask a question out loud. AssemblyAI transcribes it and speaks the reply. Parallel finds sources for an open question or checks a yes/no claim. LiveKit connects the pieces in your terminal.

## Start talking

You'll need Git, [uv](https://docs.astral.sh/uv/getting-started/installation/), an [AssemblyAI key](https://www.assemblyai.com/dashboard) and a [Parallel key](https://platform.parallel.ai). The terminal demo uses hosted APIs and runs without a LiveKit account.

```sh
git clone https://github.com/hsingh-aai/assemblyai-parallel-voice-agent.git
cd assemblyai-parallel-voice-agent
uv sync --frozen
cp .env.example .env.local
```

Paste your two keys into `.env.local`. On Windows, use `copy .env.example .env.local` in Command Prompt. In an interactive terminal in the repo folder, run:

```sh
uv run python src/agent.py console --log-level info
```

Allow microphone access when prompted. In a noisy room, start in text mode:

```sh
uv run python src/agent.py console --text --log-level info
```

After the greeting, try these in the same conversation:

1. **“What changed in the latest stable Python release?”** Watch for **Search** and a source URL in the terminal. The agent uses the excerpts to summarize what changed.
2. **“Does that version offer a free-threaded build?”** Watch for **Decisions**, the estimated probability that the claim is true, and a source URL. The agent carries the version over from your first question. If the evidence is inconclusive, it should say so.

The terminal shows the recognized words on voice turns. Source links in the trace are retrieved evidence you can inspect. Press Ctrl+C to quit.

## Make it yours

Build a library compatibility assistant. In `.env.local`, set `AGENT_GREETING="Which library are you working with?"`. In [src/agent.py](src/agent.py), add this line inside `INSTRUCTIONS`:

> Help developers check package compatibility. Ask which package and version they use if either is ambiguous. Prefer official release notes and package metadata.

Restart the agent. Try “What changed in the latest stable release of NumPy?” followed by “Does that version support Python 3.13?” Then substitute a library your team actually uses.

To reuse Search or Decisions in a CLI, bot, or web backend, copy [src/parallel_api.py](src/parallel_api.py) and install `parallel-web`. It reads `PARALLEL_API_KEY` from the environment. [scripts/try_parallel.py](scripts/try_parallel.py) shows how to call `search(objective, queries)`, `decide(entity, question)`, and close the client. [src/parallel_tools.py](src/parallel_tools.py) wraps those same calls for voice and plays filler during slower requests.

## If you get stuck

- **Saw a console deprecation notice?** The locked LiveKit version supports this command. Wait for the greeting before speaking or typing.
- **No transcript or no sound?** Try text mode above. To choose a microphone or speaker, run `uv run python src/agent.py console --list-devices`, then pass `--input-device` or `--output-device` with its name. Check your terminal's microphone permission.
- **Gateway access error after the greeting?** Check your AssemblyAI key. If the error names a restricted gateway model, set `LLM_MODEL` in `.env.local` to an account-enabled option that supports streaming and tools. [AssemblyAI gateway options](https://www.assemblyai.com/docs/llm-gateway/available-models)
- **Search or Decisions failed?** Check your Parallel key and available credits. Run either example below to see the API response independently of voice.

```sh
uv run python scripts/try_parallel.py "Find the latest stable Python release notes." --query "Python stable release notes"
uv run python scripts/try_parallel.py --decision "Python 3.13, python.org" "Does Python 3.13 offer a free-threaded build?"
```

Run `uv run pytest` for the tests. Tests with configured keys make real API calls. For browser rooms and deployment, see [other ways to run the agent](docs/advanced.md).

Speech playback uses the [AssemblyAI streaming TTS plugin](https://github.com/tom-aai/assemblyai-livekit-tts).
