# Other ways to run the agent

## Browser or room

Install the LiveKit server and CLI first (on macOS, `brew install livekit livekit-cli`). Start the local server:

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

### Direct API or Parallel MCP

Set `PARALLEL_TOOL_SOURCE`:

- `api` (default): the tools in `src/parallel_tools.py`. Lowest latency; you control
  modes, result size, fillers and prompts.
- `mcp`: the hosted [Parallel MCP server](https://docs.parallel.ai/integrations/mcp/quickstart)
  (`web_search`, `web_decisions`). No tool code to maintain. It works without a key at lower
  rate limits; with `PARALLEL_API_KEY` set it bills your account.

## Local vs. LiveKit Cloud stack

`AGENT_STACK` picks the speech and LLM providers:

| | `local` (default) | `cloud` |
| --- | --- | --- |
| STT | AssemblyAI Universal-3.6 Pro, called directly | AssemblyAI Universal-3.5 Pro via LiveKit Inference |
| Turn detection | AssemblyAI end-of-turn | LiveKit turn detector |
| Interruptions | Silero VAD (on-device) | LiveKit adaptive interruption |
| LLM | [AssemblyAI LLM Gateway](https://www.assemblyai.com/docs/llm-gateway/quickstart) | LiveKit Inference |
| TTS | AssemblyAI Streaming TTS | AssemblyAI Streaming TTS |
| Noise cancellation | none | ai-coustics |
| Accounts | AssemblyAI + Parallel | + LiveKit Cloud |

## Deploy to LiveKit Cloud

```bash
lk cloud auth
lk agent create
```

This builds the [`Dockerfile`](../Dockerfile). Add `ASSEMBLYAI_API_KEY` and
`PARALLEL_API_KEY` as secrets (`lk agent update-secrets`). Set `AGENT_STACK=cloud` to
use LiveKit Inference and ai-coustics, or keep `local` to call AssemblyAI directly.

## Credits

- AssemblyAI Streaming TTS plugin and latency reporter:
  [tom-aai/assemblyai-livekit-tts](https://github.com/tom-aai/assemblyai-livekit-tts)
- [Parallel docs](https://docs.parallel.ai) · [AssemblyAI docs](https://www.assemblyai.com/docs) ·
  [LiveKit Agents docs](https://docs.livekit.io/agents/)

## Inspect latency

Set `AGENT_METRICS=1` in `.env.local` and restart to see per-turn timings.
