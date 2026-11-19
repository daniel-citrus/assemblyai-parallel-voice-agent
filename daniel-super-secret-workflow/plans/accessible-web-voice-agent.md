# Voice web search for blind users

## Overview

This turns the starter into a voice assistant a blind person can use to search the web and hear a page's pictures described. Today, `src/agent.py` answers with Parallel Search, Fetch and Decisions through hosted MCP, and `web/index.html` lists each tool call. The three tools stay. The instructions change for callers who can't see the screen: a quick answer first, sources named aloud, and follow-ups on the same topic. Descriptions come from text, not a vision model, because the AssemblyAI gateway accepts only text. Parallel Fetch drops images and their alt text from its markdown but keeps nearby captions. So a new `page_images` tool reads a page's HTML itself. It returns the meaningful images in order, with their alt text, captions and surrounding text. The gateway LLM speaks the gist first, then details, and says what the description is based on. It never claims to see an image. When a page doesn't describe one, the agent says so and offers to look elsewhere. During a slow lookup, it says what it is doing.

The browser page becomes an accessible front end built around an animated ASCII figure. The figure shows each state: listening, thinking, speaking, searching, reading, deciding, or looking at images. Screen readers hear tool activity and errors, but not the transcript the caller already hears. Every control works from the keyboard, and reduced motion stops the animation. The page also lists the images found, with their text.

Out of scope: vision models, uploaded photos, the camera and sound cues. No new API keys are needed, and `httpx` becomes a declared dependency. Many images lack alt text or captions, so some descriptions will be thin. When a site blocks direct requests, the agent falls back to Fetch captions.

Two slices, both ready now, two workers. The agent side and the page share no files and follow `## Shared`.

## Shared

The `page_images` tool takes one `url` argument and returns a JSON object as its output string. `page` is the final URL after redirects, and `title` is the page title or null. `images` holds at most 8 entries in page order, with the page's main image first. The main image is the `og:image`, or else the first large image inside `main` or `article`. `skipped` counts the images left out as decorative. `note` is null, or a short reason when the page offered nothing useful.

Each image has `n` (its 1-based position in the list) and `src` (an absolute URL). It also has `alt`, `caption` and `context`, where `context` is the nearest heading plus the surrounding text. Each of those three is a string of at most 300 characters, or null.

Events stay on the `parallel.events` topic in the shapes `src/web_events.py` sends today. Some tools return output that parses as a JSON object containing an `images` list. Their `tool_ended` event gains an `images` field with that list, capped at 8 entries with the fields above. Tools whose output isn't JSON send no `images` field. `output` is still cut at 2,000 characters, so the page reads images only from `images`. The agent name stays `parallel-search-agent`, and the page reads the agent's state from the `lk.agent.state` attribute, as it does today.

In this checkout, `uv run` fails because the path contains a colon. Run `uv sync --frozen`, or `uv lock` after changing `pyproject.toml`. Then run `.venv/bin/python -m pytest -q` and `.venv/bin/ruff check .`.

## Work breakdown

| Slice | Covers | Touches | After | Size |
| --- | --- | --- | --- | --- |
| agent | page_images tool, instructions for blind callers, events, docs | src/page_images.py, src/agent.py, src/voice_mcp.py, src/web_events.py, tests/test_page_images.py, tests/test_agent.py, tests/test_voice_mcp.py, tests/test_web_events.py, tests/test_agent_live.py, pyproject.toml, uv.lock, README.md, docs/advanced.md, AGENTS.md | - | large |
| page | accessible page with an animated ASCII figure | web/index.html | - | large |

## agent

`src/page_images.py` exports the `page_images` function tool and the parsing behind it. The tool takes one http or https URL. It downloads the page with `httpx`, which this slice adds to `pyproject.toml` and `uv.lock`, sending a descriptive User-Agent. It parses the page with the standard library's `html.parser`. For each image, it gathers:

- the alt text, `title` and `aria-label`
- the `figcaption` of the figure the image is in
- the nearest heading and the surrounding text
- the page's `og:image`, `og:image:alt` and `twitter:image:alt`
- the JSON-LD image `caption` or `description`

It skips decorative images: an empty alt, `role="presentation"`, `aria-hidden`, a declared width or height under 64 pixels, or a filename or class that marks an icon, logo, spacer or tracking pixel. It returns the JSON in `## Shared`. A request times out after 10 seconds and stops after 3 MB or 3 redirects. Any host that resolves to a loopback, private, link-local or reserved address is refused, checked again at every redirect. A URL that serves an image file directly returns that one image, with its filename's words as `context` and a `note` saying the page has no text about it. Failures raise `ToolError` with a reason the agent can say aloud.

`src/agent.py` registers `page_images` next to the Parallel toolset and rewrites `INSTRUCTIONS` and the default greeting for blind callers:

- Answer quickly and directly, name sources aloud, and keep follow-ups on the same subject without asking the caller to repeat it.
- For "what does it look like" or "describe the picture", find a page that shows it, call `page_images`, and give the gist in one sentence. Then describe the subject, the action, the setting, the colors and any text in the image, but only as far as the page's words support them.
- Say what the description comes from. Never say you can see an image, and never invent visual details.
- When there's nothing to go on, say so and mention how many images were skipped. Offer to search for a description elsewhere, such as the image's source or credit page.
- When `page_images` fails, use the captions that `web_fetch` returns.
- Image descriptions can run to five sentences and end by offering more detail. Other replies keep today's limit of one to three sentences.

`src/voice_mcp.py` gives each slow lookup its own acknowledgment in place of one fixed phrase: searching the web, reading the page, weighing the evidence, or looking at the page's pictures. It exports the helper so `page_images` uses the same acknowledgment. `src/web_events.py` adds the `images` field from `## Shared`. `README.md`, `docs/advanced.md` and `AGENTS.md` describe the new purpose and include an image example.

- Given an HTML fixture served through `httpx.MockTransport`, `page_images` returns the fixture's figure images in page order, with their alt text, captions and nearest heading, and the `og:image` first. It leaves out an empty-alt spacer, a 1×1 tracking pixel and a logo, and counts them in `skipped`.
- An image with no alt text or caption still appears, with `alt` and `caption` null and its surrounding text in `context`.
- Text fields are cut to 300 characters, and the list stops at 8 images.
- `http://localhost`, `http://127.0.0.1`, `http://10.0.0.5`, a `file:` URL, and a redirect to a private address each raise `ToolError`, and the transport never receives a request for the refused address.
- A page over 3 MB, a timeout, and an HTTP 403 each raise `ToolError` with a reason that can be read aloud.
- A direct image URL returns one image, with its filename's words in `context` and a `note`.
- `tests/test_agent.py` builds the agent without network calls and finds `page_images` in its tools and its instructions.
- `tests/test_voice_mcp.py` shows that each tool name gets its own acknowledgment, an unknown tool gets a generic one, and a fast lookup still says nothing.
- In `tests/test_web_events.py`, a `tool_ended` event whose output is the `## Shared` JSON carries `images`. Non-JSON output carries no `images` field, and more than 8 images are cut to 8.
- With an AssemblyAI key, `.venv/bin/python -m pytest -q tests/test_agent_live.py` still passes its three tool turns. A new turn asks for a description of the main photo on the Wikipedia article about the Golden Gate Bridge. It calls `page_images`, and the reply mentions the bridge without saying "I can see". Without the key, the test is skipped.
- `.venv/bin/python -m pytest -q` passes with no keys set and the live test skipped, and `.venv/bin/ruff check .` reports nothing.

## page

`web/index.html` becomes the assistant's accessible front end. It keeps the current LiveKit connection, transcript, text input and tool timeline code, and the existing color tokens and Atkinson Hyperlegible fonts. The header holds an animated ASCII figure, original art, in a fixed grid of at most 28 columns and 10 rows, with the state word next to it.

The figure's scene follows the agent. The `lk.agent.state` attribute gives listening, thinking and speaking. A running tool overrides that state until its `tool_ended` arrives: searching for `web_search`, reading for `web_fetch`, deciding for `web_decisions`, and looking at images for `page_images`. Connecting, waiting for the agent, ended and error each have a scene of their own. The speaking scene follows the agent's audio level when LiveKit reports one. The figure animates at a calm rate and pauses while the tab is hidden. Under `prefers-reduced-motion`, it shows one still frame per state. The figure is `aria-hidden`, and the visible state word carries its meaning.

A polite live region announces tool activity in short phrases, such as "Searching the web for free-threaded Python" or "Found three images on nasa.gov", and announces errors. It doesn't announce listening, speaking or transcript text, because the caller already hears those. In the timeline, a `page_images` call lists the images it found. Each one has a lazy-loaded thumbnail that requests the image with no referrer. The thumbnail's alt is the page's own alt text or caption, or "No description on the page", and its text and page link sit next to it. The example buttons cover Search, Images and Decisions. Use the frontend-design and animate skills for the visual and motion direction, then run the d-ui pass for accessibility.

- Each state shows its own scene and state word. A `tool_started` for `web_search` switches the scene to searching, and its `tool_ended` returns to the agent's current `lk.agent.state`.
- While two tools overlap, the figure shows the one that started later until it ends, then the other until both end.
- An unknown tool name shows the thinking scene and its raw name in the timeline.
- Frames never change the figure's size or shift the page layout.
- Under `prefers-reduced-motion: reduce`, the figure doesn't change frames while the state stays the same.
- The live region gets the tool's subject when a tool starts, the image count when `page_images` ends, and each error message. It never gets transcript text.
- A `page_images` result renders one thumbnail per entry in `images`, with the alt text described above. A thumbnail that fails to load is hidden without a console error.
- The Tab key reaches every control, each one shows a visible focus ring, and nothing traps focus. On load, Start session has focus. After the page joins the room, the text input has focus.
- At 375 px wide, the figure fits with no horizontal page scroll, and text meets WCAG AA contrast in both light and dark color schemes.
- An axe-core scan of the intro screen and of a session reports no serious or critical violations.

## After merge

- Run `livekit-server --dev --config web/livekit.yaml`, `.venv/bin/python src/agent.py dev` and `.venv/bin/python web/server.py`. Then ask by voice at http://localhost:8090: "What does the Golden Gate Bridge look like at night?" The agent searches, looks at a page's images and speaks a description that names where it came from. Meanwhile, the figure moves through searching, looking at images and speaking.
- With VoiceOver on, Tab through the page and start a session. VoiceOver announces tool activity without reading the agent's replies a second time.
- Ask about a page whose main image has no alt text or caption. The agent says the page doesn't describe it and offers to look elsewhere.
- In `.venv/bin/python src/agent.py console --text`, paste a public article URL and ask what its photos show. The agent describes them from the page's text.
- `.venv/bin/python -m pytest -q tests/test_agent_live.py` passes with an AssemblyAI key. A skip means the live path is unverified.
