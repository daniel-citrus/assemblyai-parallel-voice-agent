# AssemblyAI × Parallel voice agent starter

A [LiveKit Agents](https://docs.livekit.io/agents/) voice agent that answers questions
from the **live web** using [Parallel](https://parallel.ai), with **AssemblyAI** for
speech-to-text and text-to-speech.

```
caller ──► AssemblyAI Universal-3.5 Pro STT ──► LLM ──► AssemblyAI Streaming TTS ──► caller
                                                 │
                                   web_search · read_webpage · deep_research
                                                 │
                                         Parallel Search / Extract / Responses
```

Ask it "who won last night's game?", "what's the weather in Lisbon this weekend?" or
"compare the two cheapest flights to Tokyo next month", and it searches before it answers.

## What's in here

| File | What it does |
| --- | --- |
| [`src/agent.py`](src/agent.py) | The agent: STT/LLM/TTS session, voice-tuned prompt, tool wiring. |
| [`src/parallel_tools.py`](src/parallel_tools.py) | Parallel tools for LiveKit, tuned for voice latency. |
| [`src/metrics.py`](src/metrics.py) | Per-turn latency box (EOU, STT, LLM TTFT, TTS TTFB, end-to-end). |
| [`scripts/try_parallel.py`](scripts/try_parallel.py) | Run a search or research call without LiveKit to check your key and latency. |
| [`tests/`](tests) | Offline unit tests plus a live search test (runs when `PARALLEL_API_KEY` is set). |
| [`Dockerfile`](Dockerfile) | Image for deploying to LiveKit Cloud. |

## Requirements

- Python 3.10–3.13 and [`uv`](https://docs.astral.sh/uv/)
- [LiveKit Cloud](https://cloud.livekit.io/) project and the LiveKit CLI 2.18.8+ (`brew install livekit-cli`)
- [AssemblyAI API key](https://www.assemblyai.com/dashboard) (Streaming TTS)
- [Parallel API key](https://platform.parallel.ai)

## Quickstart

```bash
git clone https://github.com/hsingh-aai/assemblyai-parallel-voice-agent.git
cd assemblyai-parallel-voice-agent
uv sync
```

```bash
lk cloud auth                 # writes LIVEKIT_URL / KEY / SECRET for your project
cp .env.example .env.local    # then fill in ASSEMBLYAI_API_KEY and PARALLEL_API_KEY
```

```bash
uv run python src/agent.py download-files   # once: turn-detector + noise-cancel models
```

```bash
uv run python scripts/try_parallel.py "latest LiveKit Agents release"   # sanity check Parallel
```

```bash
uv run python src/agent.py console   # talk to it in your terminal
```

To use a browser frontend or the [Agent Console](https://docs.livekit.io/testing/agent-console/)
instead, run `uv run python src/agent.py dev`.

> If you keep keys in `~/.zshrc`, make sure they're **exported**
> (`export PARALLEL_API_KEY=...`), or Python won't see them.

## The Parallel tools

The LLM picks the cheapest tool that can answer:

| Tool | Parallel API | Typical latency | Use for |
| --- | --- | --- | --- |
| `web_search` | [Search](https://docs.parallel.ai/search/search-quickstart) (`fast` mode) | ~0.7 s | Most questions: news, facts, prices, people, schedules |
| `read_webpage` | [Extract](https://docs.parallel.ai/extract/extract-quickstart) | ~1–3 s | A URL the caller gives, or a result that needs more detail |
| `deep_research` | [Responses](https://docs.parallel.ai/responses-api/responses-quickstart) (`low` effort) | ~5–10 s | Comparisons and multi-step questions; returns a cited, synthesized answer |

Voice-specific choices:

- **Small results.** `max_chars_total` defaults to 4,000 characters and 5 results. Every
  token the LLM reads delays its first word, so keep this tight.
- **Filler only when needed.** Tools wrap the API call in `RunContext.with_filler`, so
  "One sec, let me look that up." plays only if the call runs long enough to leave a
  noticeable silence. `deep_research` sends up to three spaced progress lines.
- **Good queries.** Tool descriptions follow Parallel's
  [best practices](https://docs.parallel.ai/search/best-practices): a standalone
  `objective` plus 1–3 short keyword queries, rather than the raw question twice.
- **Session grouping.** All calls in one LiveKit room share a Parallel `session_id`.
- **Today's date** is in the system prompt so "latest" and "this weekend" resolve correctly.

### Direct API or Parallel MCP

Set `PARALLEL_TOOL_SOURCE` in `.env.local`:

- `api` (default): the tools in `src/parallel_tools.py`. Lowest latency; you control
  modes, result size, fillers and prompts.
- `mcp`: the hosted [Parallel MCP server](https://docs.parallel.ai/integrations/mcp/quickstart)
  at `https://mcp.parallel.ai/mcp` (`web_search`, `web_fetch`). No tool code to maintain.
  It works without a key at lower rate limits; with `PARALLEL_API_KEY` set it sends the
  key as a bearer token and bills your account.

## Configuration

All optional; see [`.env.example`](.env.example).

| Variable | Default | Notes |
| --- | --- | --- |
| `PARALLEL_SEARCH_MODE` | `fast` | `turbo` (~200 ms, English/Japanese only), `fast`, `basic`, `advanced` (~3 s) |
| `PARALLEL_MAX_CHARS` | `4000` | Total excerpt characters per search |
| `PARALLEL_MAX_RESULTS` | `5` | Results per search |
| `PARALLEL_RESEARCH_EFFORT` | `low` | `low`, `medium` (~15–20 s), `high` (~30–60 s) |
| `PARALLEL_TOOL_SOURCE` | `api` | `api` or `mcp` |
| `LLM_MODEL` | `google/gemma-4-31b-it` | Any [LiveKit Inference LLM](https://docs.livekit.io/agents/models/llm/) that supports tool calling |
| `ASSEMBLYAI_TTS_VOICE` | `aai-violet` | See the [voice list](https://github.com/tom-aai/assemblyai-livekit-tts#voices) |

## Latency

Every turn logs a summary like this, so you can see what each search costs:

```
┌──────────────────────────────────────────────┐
│             Turn latency summary             │
├──────────────────────────────────────────────┤
│ End of utterance delay             312.4 ms │
│ Transcription delay                 88.1 ms │
│ LLM time to first token            402.7 ms │
│ TTS time to first byte             141.9 ms │
├──────────────────────────────────────────────┤
│ End-to-end turn latency          1,694.2 ms │
└──────────────────────────────────────────────┘
```

Search turns add one LLM round trip plus the Parallel call. To make them faster, try
`PARALLEL_SEARCH_MODE=turbo` or a smaller `PARALLEL_MAX_CHARS`.

## Tests

```bash
uv run pytest
```

The live search test runs only when `PARALLEL_API_KEY` is set.

## Deploy to LiveKit Cloud

```bash
lk agent create
```

This builds the [`Dockerfile`](Dockerfile). Add `ASSEMBLYAI_API_KEY` and
`PARALLEL_API_KEY` as secrets (`lk agent update-secrets`); LiveKit Cloud provides its own
credentials.

## Credits

- AssemblyAI Streaming TTS plugin and latency reporter:
  [tom-aai/assemblyai-livekit-tts](https://github.com/tom-aai/assemblyai-livekit-tts)
- [Parallel docs](https://docs.parallel.ai) · [LiveKit Agents docs](https://docs.livekit.io/agents/)
