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

## Deploy to LiveKit Cloud

```bash
lk cloud auth
lk agent create
```

This builds the [`Dockerfile`](../Dockerfile). Add `ASSEMBLYAI_API_KEY` and
`PARALLEL_API_KEY` as secrets (`lk agent update-secrets`). The deployed worker uses the same AssemblyAI and Parallel APIs as the terminal demo.
