# Live presidential debate fact checker

## Overview

This turns the voice starter into a live fact checker for presidential debates. Today, `src/agent.py` is a conversational assistant that calls Parallel Search, Fetch and Decisions through hosted MCP. Instead, the agent will pull a debate's audio from a URL that yt-dlp or ffmpeg can open, such as a YouTube live stream, or from a local recording. AssemblyAI transcribes it with speaker labels, and the gateway LLM picks out checkable factual claims. Each claim gets one Parallel Decisions question with a fixed rubric (accurate, missing context, misleading, false, unverifiable), the same for every speaker. The agent ignores the microphone and doesn't converse. It speaks only when a claim comes back misleading or false with a probability of at least 0.8. Then it says one sentence of at most 15 words, so it doesn't talk over the debate. The detail goes to a fact-check panel on the browser page, sized to sit beside the debate. For each claim, the panel shows the words spoken, the claim as checked, a confidence score, and the source excerpts behind it. You paste the stream URL and an optional debate description there. In the console, `DEBATE_URL` picks the stream and the log shows each verdict.

Compatibility: `PARALLEL_API_KEY` and ffmpeg become required, and the agent is renamed `debate-fact-checker`. The three-tool assistant is removed, with `src/voice_mcp.py`, `src/metrics.py` and `docs/decision-prompts.md`. Speakers keep their diarization labels; naming them and asking the agent questions are out of scope.

Risks: Decisions latency is undocumented, so verdicts may trail the claim by tens of seconds. Three checks run at once and the rest wait in order. Each claim is a paid Decisions call. If the gateway model returns malformed JSON, that turn is skipped. Crosstalk can mix up the speaker labels.

Four slices, three ready now, three workers. Audio ingest, the checker and the page share no files and follow `## Shared`, so they start together. The agent slice wires audio and the checker into the session, so it waits for both.

## Shared

The agent publishes JSON events on the reliable LiveKit data topic `factcheck.events`, which replaces `parallel.events`. The checker produces `claim`, `verdict` and `alert` events as dicts. The agent adds `status`, `transcript` and `error` events and publishes all of them. A `status` event has `state` set to `starting`, `listening`, `ended` or `failed`, plus an optional `message`. A `transcript` event has `id`, `speaker` (a diarization label such as `A`, or null when AssemblyAI returns none), `text`, `final` (boolean) and `at` (seconds since the stream started). Interim updates reuse their turn's `id`. A `claim` event has `id`, `turn_id`, `speaker`, `quote` (the words as spoken) and `claim` (the standalone restatement that was checked). A `verdict` event has the claim's `id`, `label`, `probability`, `probabilities`, `confidence`, `sources` and `seconds` (how long the check took). `probability` is the chosen label's probability, and the page shows it as the confidence score. `probabilities` maps each of the five labels to its probability. `confidence` is the model-reported confidence Decisions returns, or null when it returns none. On a refusal, `probability`, `probabilities` and `confidence` are all null. `sources` holds at most three `{title, url, excerpt}` objects, taken from the citations Decisions grounded the verdict on; `title` and `excerpt` may be null, and an excerpt is at most 400 characters. An `alert` event has the claim's `id` and `text`, the sentence the agent speaks. An `error` event keeps today's `source`, `message` and `recoverable` fields from `src/web_events.py`. The only labels are `accurate`, `missing_context`, `misleading`, `false` and `unverifiable`. A Decisions refusal becomes `unverifiable` with no scores.

The page starts a session with `POST /token` and a JSON body `{"url": "...", "context": "..."}`, where `context` is optional. `web/server.py` returns the `serverUrl`, `room` and `token` fields it returns today, or HTTP 400 with `{"error": "..."}` when `url` is not an http or https URL. It passes the body as a JSON string in the agent dispatch metadata. The agent reads `ctx.job.metadata` and falls back to the `DEBATE_URL` and `DEBATE_CONTEXT` environment variables when the metadata is empty. The dispatched agent name is `debate-fact-checker`.

## Work breakdown

| Slice | Covers | Touches | After | Size |
| --- | --- | --- | --- | --- |
| audio | stream and file ingest through ffmpeg | src/debate_audio.py, tests/test_debate_audio.py, pyproject.toml, uv.lock, Dockerfile | - | medium |
| checker | claim extraction, Decisions verdicts, spoken corrections | src/fact_check.py, src/parallel_api.py, tests/test_fact_check.py, tests/test_parallel_tools.py, tests/test_agent_live.py | - | large |
| page | stream form, fact-check panel, live transcript | web/index.html, web/server.py, tests/test_web_server.py | - | large |
| agent | session wiring, events, removals, docs | src/agent.py, src/web_events.py, src/voice_mcp.py, src/metrics.py, tests/test_agent.py, tests/test_web_events.py, tests/test_voice_mcp.py, .env.example, README.md, docs/advanced.md, docs/decision-prompts.md, AGENTS.md | audio, checker | medium |

## audio

`src/debate_audio.py` turns a source string into live PCM audio for the STT stream. It exports `debate_audio(source: str) -> AsyncIterator[rtc.AudioFrame]`, which yields 16 kHz mono 16-bit frames of about 50 ms decoded by an `ffmpeg` subprocess. A local file path plays at real time, so a recording behaves like a live broadcast. An http or https page URL that yt-dlp recognizes, including a YouTube live stream, is resolved to its audio stream first. HLS and direct media URLs go straight to ffmpeg. This slice adds `yt-dlp` to `pyproject.toml` and `uv.lock` and installs ffmpeg in the `Dockerfile`.

- A one-second WAV that the test writes decodes to 16 kHz mono frames totaling about one second. The test skips when ffmpeg is not installed.
- A local file is never yielded faster than real time.
- When the source ends, the iterator finishes normally.
- With no ffmpeg on `PATH`, iteration fails before the first frame. The error names ffmpeg and how to install it.
- An unreachable or unsupported URL raises an error that names the source and gives the ffmpeg or yt-dlp reason. It never hangs or ends silently.
- Breaking out of the iteration or cancelling its task ends the ffmpeg process.
- `uv sync --frozen` succeeds with the updated lock file.

## checker

`src/fact_check.py` exports `FactChecker(llm, parallel, *, context="", on_event, speak_threshold=0.8, max_concurrent=3)`, with `add_turn(turn_id, speaker, text, at)` and `aclose()`. `llm` is the gateway LLM returned by `build_llm()` in `src/agent.py`, and `parallel` is a `ParallelAPI`. For each final turn, the LLM gets the previous few turns and `context` as background and returns the checkable factual claims as JSON. Checkable claims include statistics, records, votes, dates and quotes, each restated so it stands alone. Opinions, promises, predictions, questions and moderator procedure produce nothing. Each new claim emits a `claim` event. Then `ParallelAPI.check_claim(claim, context)`, a new method in `src/parallel_api.py`, sends one Decisions `choice` question with the five-label rubric, putting the debate context and today's date in `state`. Its label, per-label probabilities, confidence and citations become a `verdict` event. When the label is `misleading` or `false` at or above `speak_threshold`, and the verdict arrives within 120 seconds of its turn, the LLM writes one plain spoken sentence of at most 15 words that gives the correction and names a source. It is emitted as an `alert`. If the LLM's reply is empty or runs over 15 words, the alert falls back to a fixed sentence. It says the claim is false or misleading, according to the first source's title, such as "That claim is false, according to Reuters." `tests/test_agent_live.py` becomes the live check for this path.

- With a fake LLM and a mocked Decisions call, a turn containing one claim emits `claim` and then `verdict` with the same `id`, in the shapes `## Shared` gives.
- Malformed LLM JSON emits nothing for that turn and logs a warning, and later turns are still checked.
- The same claim returned twice in one session is checked once.
- No more than `max_concurrent` Decisions calls run at once. Extra claims are checked in the order they arrived.
- A verdict carries the chosen label's probability, all five label probabilities, and Decisions' confidence, all taken from the Decisions answer. Its sources come from the response's citations, with their excerpts.
- A refusal from Decisions gives `unverifiable` with no scores and no alert.
- An LLM correction longer than 15 words is replaced with the fallback sentence.
- With the default threshold, `false` at 0.9 emits an alert. `false` at 0.6, `missing_context` at any probability, and a verdict that arrives more than 120 seconds after its turn do not.
- A failed Decisions call emits a recoverable `error` event for that claim, and later claims are still checked.
- `aclose()` cancels checks that haven't started and returns without waiting on the network.
- `check_claim` posts to `/v1/decisions` with one `choice` question whose criteria keys are the five labels. `decide` and its existing test are unchanged.
- With both API keys set, `uv run pytest -q tests/test_agent_live.py` feeds in a turn that holds one well-documented false claim and one opinion. It gets back one claim labeled `false` or `misleading` with an https source. Without both keys, the test is skipped.

## page

`web/index.html` and `web/server.py` become the fact checker's page, keeping the current page's color tokens, fonts and LiveKit connection code. The start screen has a stream URL field, an optional debate description and a start button. The microphone, the text box and the three-tool prompt buttons go away. During a session, the main view is a fact-check panel, newest check first, that still works as a narrow window beside the debate. Each check shows the words as spoken with the speaker label, the claim as checked, and "Checking" until its verdict arrives. It then shows the verdict label and the confidence score as a percentage, with a bar for each label's probability. Decisions' model confidence appears too, when it returns one. Below that come the sources behind the score, each with its title, its excerpt and a link that opens in a new tab. Every label has its own color, and the label text appears too, so color isn't the only signal. A check that got an `alert` shows the sentence the agent spoke. The live transcript, labeled by speaker with interim text muted, is secondary and takes less space than the panel. The agent's audio plays, and the existing "Play audio" prompt appears when the browser blocks it. A line on the page says the verdicts are automated and readers should check the sources.

- A URL that isn't http or https shows the server's 400 message, and no session starts.
- Events in the `## Shared` shapes render the transcript, claim, verdict, alert, status and error correctly. A verdict for an unknown claim id is ignored without a console error.
- A verdict shows the checked claim, the confidence score as a percentage, all five label probabilities, and each source's title, excerpt and link. A refusal shows "Couldn't verify" with no score.
- The newest check appears at the top of the panel.
- `ended` and `failed` statuses show their message and offer a new session.
- The page never asks for microphone permission.
- At 375 px wide there is no horizontal page scroll, and the page is readable in both light and dark color schemes.
- In `tests/test_web_server.py`, a valid `POST /token` returns a token whose dispatch names `debate-fact-checker` and carries the request body as metadata. `GET /` still serves the page.

## agent

`src/agent.py` becomes the debate fact checker under the agent name `debate-fact-checker`. On each job it reads the source and context from dispatch metadata or the environment, and it requires `PARALLEL_API_KEY`. It starts an `AgentSession` with only the AssemblyAI TTS voice: no microphone input and no replies. It runs `debate_audio` into `assemblyai.STT` with `speaker_labels=True`, sends `status` and `transcript` events, passes final turns to `FactChecker`, and speaks each `alert` with `session.say`. Alerts play one at a time. An alert whose claim is more than 120 seconds old when its turn comes is skipped. `src/web_events.py` publishes every `## Shared` event on `factcheck.events` and trims sources and excerpts to their limits. It still skips console jobs, as `ctx.is_fake_job()` does today. In the console, the log shows transcript lines, claims, and verdicts with their confidence score and top source. Keep `build_llm()`, `LLM_MODEL`, `STT_MODEL` and `TTS_VOICE`. Delete `src/voice_mcp.py`, `src/metrics.py`, `tests/test_voice_mcp.py` and `docs/decision-prompts.md`. Rewrite `README.md`, `docs/advanced.md`, `AGENTS.md` and `.env.example` for the new setup. Cover installing ffmpeg, both keys, `DEBATE_URL`, `DEBATE_CONTEXT`, `FACT_CHECK_SPEAK_THRESHOLD`, running from the console and the browser, and troubleshooting ffmpeg, yt-dlp and Decisions errors.

- `uv run pytest -q` passes with no keys set, with the live tests skipped, and `uv run ruff check .` reports nothing.
- `tests/test_agent.py` builds the agent's pieces without any network calls.
- With no source in the metadata or in `DEBATE_URL`, the agent logs and sends a `failed` status that names both ways to set one, and it doesn't start STT.
- Without `PARALLEL_API_KEY`, the agent logs and sends a `failed` status that names the key.
- An ingest error partway through sends a `failed` status with the reason.
- When the stream ends, the agent sends an `ended` status, and claims already queued still get verdicts.
- The agent says nothing except alerts.
- A second alert waits until the first finishes. An alert whose claim is more than 120 seconds old by then is shown on the page but not spoken.
- `tests/test_web_events.py` checks the topic name and that sources are trimmed to three and excerpts to 400 characters.

## After merge

- With both keys and ffmpeg installed, set `DEBATE_URL` in `.env.local` to a recorded debate clip and run `uv run python src/agent.py console`. It logs speaker-labeled transcript lines, claims and verdicts, and speaks a one-sentence correction after a false claim.
- With `livekit-server --dev --config web/livekit.yaml`, `uv run python src/agent.py dev` and `uv run python web/server.py` running, paste a YouTube debate replay URL at http://localhost:8090. While it plays, the fact-check panel fills in with each claim, its confidence score and its source excerpts, and the short spoken correction plays in the browser.
- A YouTube live stream URL works the same way while the stream is live.
- `uv run pytest -q tests/test_agent_live.py` passes with both keys set. A skip means the live path is unverified.
- `docker build .` succeeds, and `ffmpeg -version` runs inside the image.
