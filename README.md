# AssemblyAI + Parallel voice assistant for blind users

Talk to a voice assistant built for people who can't see the screen. It answers first, names its sources aloud, and keeps follow-ups on the same subject. Ask what something looks like and it describes a page's pictures from the page's own words. AssemblyAI handles speech and replies. Parallel’s hosted MCP server gives the agent three tools: Search finds evidence, Fetch reads a particular public page, and Decisions estimates a probability or chooses among supplied options. A fourth tool, `page_images` in [src/page_images.py](src/page_images.py), reads a page's HTML for each meaningful image's alt text, caption and surrounding text. The first conversation only needs an AssemblyAI key. [Parallel MCP](https://docs.parallel.ai/integrations/mcp/quickstart)

The agent never sees an image. The AssemblyAI gateway accepts only text, so a description is only as good as the words the page gives it. The agent says what each description is based on, and when a page has nothing to go on, it says so and offers to look elsewhere.

## Run it

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then open a terminal:

```sh
git clone https://github.com/hsingh-aai/assemblyai-parallel-voice-agent.git
cd assemblyai-parallel-voice-agent
uv sync --frozen
```

Copy `.env.example` to `.env.local`. Set `ASSEMBLYAI_API_KEY` with your [AssemblyAI key](https://www.assemblyai.com/dashboard). Leave `PARALLEL_API_KEY` empty for free, rate-limited MCP access.

```sh
uv run python src/agent.py console --log-level info
```

Allow microphone access and wait for the greeting. To type instead, add `--text` to the command. Press Ctrl+C to quit.

### Hit the free-tier rate limit?

1. Press Ctrl+C to stop the agent. Get a key from the [Parallel dashboard](https://platform.parallel.ai).
2. Open the existing `.env.local` in the repo folder. Find `PARALLEL_API_KEY=`, paste your key after the equals sign, and save the file.
3. Run the same console command again and repeat your question. On startup, the agent picks up your key and uses your Parallel account for Search, Fetch, and Decisions. No code changes are needed.

## Try the tools

1. **Search:** “What changed in the latest stable Python release?” The agent can answer directly from search excerpts.
2. **Fetch:** “Read the release notes you just cited. What do they say about upgrading?” The follow-up identifies a specific page. You can also paste a public URL in text mode.
3. **Decisions:** “How likely is it that Python 3.13 offers a free-threaded build? Give me a probability.” Decisions gathers its own evidence and estimates how likely the claim is to be true.
4. **Pictures:** “Describe the main photo on the Wikipedia article about the Golden Gate Bridge.” The agent finds the article and calls `page_images`. It gives the gist in one sentence, then the details the caption, alt text and nearby text support, and ends by offering more. Follow up with “What do the other pictures show?”

Watch the tool names in the terminal. The agent chooses when to call each one. Fetch is for a specific page or a missing detail, so a search that already answers the question needs only one call. During a slow lookup, the agent says what it is doing, such as searching the web or reading about the page's pictures.

## Watch it in the browser

The page in [web/](web/index.html) shows what the agent is doing and every tool call, and it lists the images the agent found with their text. Screen readers announce tool activity and errors, and every control works from the keyboard. It needs a local LiveKit server (on macOS, `brew install livekit`). Run each command in its own terminal from the repo folder. The config keeps audio on localhost, so a VPN or switching Wi-Fi doesn't break the connection.

```sh
livekit-server --dev --config web/livekit.yaml
uv run python src/agent.py dev
uv run python web/server.py
```

Open http://localhost:8090, select **Start session**, and allow microphone access. You can also type, or use the example buttons.

## Make it yours

Both Search and Decisions are already connected. Start with a pair of questions about the same subject. “Does Python 3.13 support free threading?” is a factual lookup. “Classify that support as stable, experimental, or explicitly unsupported” asks for a decision against supplied options. [See the prompt and tool input for this example](docs/decision-prompts.md).

Try a library compatibility assistant. Set `AGENT_GREETING="Which library are you working with?"` in `.env.local`. Add “Prefer official release notes and package metadata” to `INSTRUCTIONS` in [src/agent.py](src/agent.py). Restart and try similar questions about a library you use.

To change how pictures are found, edit [src/page_images.py](src/page_images.py). It decides which images are decorative and how much text to keep, and the picture rules in `INSTRUCTIONS` decide how they are described.

**Standalone API example.** To call Parallel directly from your own app, set `PARALLEL_API_KEY` with a [Parallel key](https://platform.parallel.ai). [parallel_api.py](src/parallel_api.py) has the two API calls and only needs `parallel-web`. [try_parallel.py](scripts/try_parallel.py) shows how to use them.

[Setup help](docs/advanced.md#troubleshooting) · [Browser and deployment options](docs/advanced.md#browser-or-room)
