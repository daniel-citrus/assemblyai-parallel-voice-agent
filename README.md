# AssemblyAI × Parallel voice agent starter

A [LiveKit Agents](https://docs.livekit.io/agents/) voice agent that answers questions
from the **live web** using [Parallel](https://parallel.ai), with **AssemblyAI** for
speech-to-text, the LLM, and text-to-speech. It runs entirely on your machine, with no
LiveKit Cloud account needed, using two API keys.

```
caller ─► AssemblyAI STT ─► LLM (AssemblyAI LLM Gateway) ─► AssemblyAI TTS ─► caller
          3.7 realtime agent       │
          + end-of-turn            ├─ web_search    → Parallel Search  (~0.7 s)
                                   ├─ read_webpage  → Parallel Extract
                                   └─ deep_research → Parallel Responses (~5-10 s)
```

A real local run (from the agent's logs):

```
USER  · Who won the most recent Formula 1 race?
        web_search objective='Find the winner of the most recent Formula 1 race in November 2026.'
AGENT · Lando Norris won the most recent Formula 1 race, the Brazil Grand Prix on November eighth...
USER  · And who came second?
AGENT · Max Verstappen came second, finishing fourteen point six seconds behind Lando Norris.
```

## What's in here

| File | What it does |
| --- | --- |
| [`src/agent.py`](src/agent.py) | The agent: session, voice-tuned prompt, local vs. cloud stack, tool wiring. |
| [`src/parallel_tools.py`](src/parallel_tools.py) | Parallel tools for LiveKit, tuned for voice latency. |
| [`src/metrics.py`](src/metrics.py) | Logs each turn's text plus a latency box (EOU, LLM TTFT, TTS TTFB, end-to-end). |
| [`scripts/try_parallel.py`](scripts/try_parallel.py) | Run a search or research call without LiveKit to check your key and latency. |
| [`tests/`](tests) | Offline unit tests, plus live end-to-end conversation tests when keys are set. |
| [`Dockerfile`](Dockerfile) | Image for deploying to LiveKit Cloud. |

## Requirements

- Python 3.10–3.13 and [`uv`](https://docs.astral.sh/uv/)
- [AssemblyAI API key](https://www.assemblyai.com/dashboard): one key covers STT, the LLM Gateway and TTS
- [Parallel API key](https://platform.parallel.ai)
- For voice in a browser or room: `brew install livekit livekit-cli` (local server + CLI)

## Quickstart (local)

```bash
uv sync
cp .env.example .env.local   # add ASSEMBLYAI_API_KEY and PARALLEL_API_KEY
```

Check that Parallel works:

```bash
uv run python scripts/try_parallel.py "latest LiveKit Agents release"
```

**Talk to it in your terminal** (uses your mic and speakers, no server needed):

```bash
uv run python src/agent.py console
```

Add `--text` to type instead of speaking.

**Or run it against a local LiveKit server**, so a browser or another participant can join:

```bash
livekit-server --dev
```

```bash
uv run python src/agent.py dev
```

```bash
lk dispatch create --room test --agent-name parallel-search-agent
```

Then join room `test` from the [Agents Playground](https://agents-playground.livekit.io/)
(URL `ws://localhost:7880`, key `devkey`, secret `secret`), or publish an audio file as a
caller: `lk room join --identity caller --publish question.ogg test`.

> **If the agent logs `failed to connect to livekit ... 502`**, something in your shell
> has set `HTTPS_PROXY`. LiveKit's worker sends all traffic through that proxy, even
> to `localhost`. Some security tools that wrap `uv` set it for child processes. Run the
> agent with the venv's Python to skip the wrapper:
> `.venv/bin/python src/agent.py dev`.

## The Parallel tools

The LLM picks the cheapest tool that can answer:

| Tool | Parallel API | Typical latency | Use for |
| --- | --- | --- | --- |
| `web_search` | [Search](https://docs.parallel.ai/search/search-quickstart) (`fast` mode) | ~0.7 s | Most questions: news, facts, prices, people, schedules |
| `read_webpage` | [Extract](https://docs.parallel.ai/extract/extract-quickstart) | ~1–3 s | A URL the caller gives, or a result that needs more detail |
| `deep_research` | [Responses](https://docs.parallel.ai/responses-api/responses-quickstart) (`low` effort) | ~5–10 s | Comparisons and multi-step questions; returns a synthesized answer with sources |

Voice-specific choices:

- **Small results.** `max_chars_total` defaults to 4,000 characters and 5 results. Every
  token the LLM reads delays its first word.
- **Filler only when needed.** "One sec, let me look that up." plays only if a call runs
  long enough to leave a noticeable silence (`RunContext.with_filler`). Fillers stay out
  of the chat history, so the LLM never sees its own filler as a reply.
- **Good queries.** Tool descriptions follow Parallel's
  [best practices](https://docs.parallel.ai/search/best-practices): a standalone
  `objective` plus 1–3 short keyword queries.
- **Session grouping.** All calls in one LiveKit room share a Parallel `session_id`.
- **Today's date** is in the system prompt, so "latest" and "today" resolve correctly.
- **A fixed greeting** starts speaking immediately, without an LLM round trip.

### Direct API or Parallel MCP

Set `PARALLEL_TOOL_SOURCE`:

- `api` (default): the tools in `src/parallel_tools.py`. Lowest latency; you control
  modes, result size, fillers and prompts.
- `mcp`: the hosted [Parallel MCP server](https://docs.parallel.ai/integrations/mcp/quickstart)
  (`web_search`, `web_fetch`). No tool code to maintain. It works without a key at lower
  rate limits; with `PARALLEL_API_KEY` set it bills your account.

## Local vs. LiveKit Cloud stack

`AGENT_STACK` picks the speech and LLM providers. Both stacks call AssemblyAI's
newest streaming model, `assemblyai-stt-3-7-realtime-agent`, directly; LiveKit
Inference only offers up to Universal-3.6 Pro.

| | `local` (default) | `cloud` |
| --- | --- | --- |
| STT | AssemblyAI 3.7 realtime agent model, called directly | Same |
| Turn detection | AssemblyAI end-of-turn | LiveKit turn detector |
| Interruptions | Silero VAD (on-device) | LiveKit adaptive interruption |
| LLM | [AssemblyAI LLM Gateway](https://www.assemblyai.com/docs/llm-gateway/quickstart) | LiveKit Inference |
| TTS | AssemblyAI Streaming TTS | AssemblyAI Streaming TTS |
| Noise cancellation | none | ai-coustics |
| Accounts | AssemblyAI + Parallel | + LiveKit Cloud |

### Choosing an LLM

The local default is `claude-haiku-4-5-20251001`. It was the fastest tool-calling model
on the LLM Gateway in our tests:

| Model | One tool call, end to end |
| --- | --- |
| `claude-haiku-4-5-20251001` | ~0.6 s |
| `gemini-3.5-flash-lite` | ~0.7 s |
| `gpt-4.1` | ~0.8 s |
| `claude-haiku-5-5` | ~1.1–1.4 s |

Any [gateway model](https://www.assemblyai.com/docs/llm-gateway/available-models) that
lists `tools` and `stream` works; set `LLM_MODEL`.

## Configuration

All optional; see [`.env.example`](.env.example).

| Variable | Default | Notes |
| --- | --- | --- |
| `AGENT_STACK` | `local` | `local` or `cloud` |
| `PARALLEL_TOOL_SOURCE` | `api` | `api` or `mcp` |
| `LLM_MODEL` | `claude-haiku-4-5-20251001` | Gateway model (local) or LiveKit Inference model (cloud) |
| `ASSEMBLYAI_STT_MODEL` | `assemblyai-stt-3-7-realtime-agent` | AssemblyAI's newest streaming model for voice agents |
| `ASSEMBLYAI_TTS_VOICE` | `aai-violet` | See the [voice list](https://github.com/tom-aai/assemblyai-livekit-tts#voices) |
| `AGENT_GREETING` | "Hi! I can look anything up…" | First thing the agent says |
| `PARALLEL_SEARCH_MODE` | `fast` | `turbo` (~200 ms, English/Japanese only), `fast`, `basic`, `advanced` (~3 s) |
| `PARALLEL_MAX_CHARS` | `4000` | Total excerpt characters per search |
| `PARALLEL_MAX_RESULTS` | `5` | Results per search |
| `PARALLEL_RESEARCH_EFFORT` | `low` | `low`, `medium` (~15–20 s), `high` (~30–60 s) |

## Latency

Each turn logs what was said and a summary. These are numbers from a local run:

```
USER  · What's the weather in San Francisco today?
AGENT · Today in San Francisco it's around fifty-seven degrees with showers...
┌──────────────────────────────────────────────┐
│             Turn latency summary             │
├──────────────────────────────────────────────┤
│ End of utterance delay             501.3 ms │
│ LLM time to first token            520.3 ms │
│ TTS time to first byte              89.8 ms │
└──────────────────────────────────────────────┘
```

A search turn adds one LLM tool call (~0.6 s) and the Parallel search (~0.7–1.7 s). For
faster turns, try `PARALLEL_SEARCH_MODE=turbo` or a smaller `PARALLEL_MAX_CHARS`.

## Tests

```bash
uv run pytest
```

- Offline tests always run.
- `tests/test_parallel_tools.py::test_live_search` runs when `PARALLEL_API_KEY` is set.
- `tests/test_agent_live.py` runs a real text conversation (LLM Gateway + Parallel) when
  both keys are set. It checks that the agent searches for current questions, doesn't
  search for small talk, and answers in plain spoken text. An LLM judges the replies.

## Deploy to LiveKit Cloud

```bash
lk cloud auth
lk agent create
```

This builds the [`Dockerfile`](Dockerfile). Add `ASSEMBLYAI_API_KEY` and
`PARALLEL_API_KEY` as secrets (`lk agent update-secrets`). Set `AGENT_STACK=cloud` to
use LiveKit Inference and ai-coustics, or keep `local` to call AssemblyAI directly.

## Credits

- AssemblyAI Streaming TTS plugin and latency reporter:
  [tom-aai/assemblyai-livekit-tts](https://github.com/tom-aai/assemblyai-livekit-tts)
- [Parallel docs](https://docs.parallel.ai) · [AssemblyAI docs](https://www.assemblyai.com/docs) ·
  [LiveKit Agents docs](https://docs.livekit.io/agents/)
