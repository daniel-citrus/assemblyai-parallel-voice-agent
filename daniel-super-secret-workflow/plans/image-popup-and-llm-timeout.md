# Image popup, relevant image and faster LLM retries

## Overview

When a caller asks about a picture, the web page today shows every image `page_images` found as thumbnails under the tool call, then turns the agent's reply into an in-chat card with the page's first image (`web/index.html`, `mainImage`, `showImage`, `claimImage`). The first image is the page's main image, not necessarily the one the caller asked about. Separately, a stalled AssemblyAI gateway request makes the caller wait in silence: LiveKit's default gives each LLM attempt 10 seconds before retrying, and in a recent session two stalled attempts cost about 22 seconds, while the gateway normally starts answering in under a second.

After this change, the agent passes the caller's subject (for example "young Joe Biden") to `page_images`, which puts the image whose alt text, caption, nearby text or file name best matches that subject first, and falls back to the main image. The page shows only that image, larger, in a popup with the agent's description streaming beneath it. The thumbnail list goes away. The popup closes when the agent starts any new lookup, when the caller presses Close or Escape, or when the session ends. A follow-up answered without a lookup keeps it open, and a follow-up that triggers a search closes it even on the same topic. Each LLM attempt now gets 5 seconds, with LiveKit's same three retries, so a stall is retried sooner. No fallback model is configured: on the current key only `gemma-4-31b` accepts requests, so another model can't be verified. If the test page's audio connection fails in Firefox, the error and the troubleshooting doc suggest Chrome or Firefox's loopback setting, not a LiveKit restart: Firefox offered only public addresses, which the localhost-only server can't reach.

Two slices, both ready now, so two workers. The agent slice (ranking, instructions, timeout, docs) and the page slice (popup) share no files. They meet only at the event contract in Shared, which the page already uses. Relevance is word matching, not vision: a page whose alt text never names the subject falls back to its main image.

## Shared

The `tool_ended` event for `page_images` keeps its current shape (`src/web_events.py`, `IMAGE_FIELDS`). Its `images[0]` is the image the agent describes first and the image the page shows. The agent slice changes only the order of that list. The page slice reads only `images[0]`.

## Work breakdown

| Slice | Covers | Touches | After | Size |
| --- | --- | --- | --- | --- |
| agent | subject ranking, instructions, LLM timeout, docs, Firefox note | src/page_images.py, src/agent.py, tests/test_page_images.py, tests/test_agent.py, tests/test_agent_live.py, docs/advanced.md | - | medium |
| page | image popup replacing the card and thumbnails, Firefox audio error | web/index.html, README.md | - | large |

## agent

`page_images` takes an optional `subject` next to `url`. `extract_images` ranks every kept image, after the main image is placed first and before the list is cut to `MAX_IMAGES`, by how many of the subject's meaningful words appear in its alt text or caption, weighted above words found in its nearby text or file name. Ties keep page order, so the main image leads when nothing matches. With no subject, the result is unchanged. The tool docstring and the "How you describe pictures" instructions in `src/agent.py` tell the model to pass the subject in a few words, and to describe the first image first.

The session's LLM connection options give each attempt 5 seconds and keep 3 retries (`SessionConnectOptions` in `livekit/agents/voice/agent_session.py`, passed as `AgentSession(conn_options=...)`). Expose them so a unit test can read them without a network call. `docs/advanced.md` troubleshooting explains the "Retrying LLM after APITimeoutError" note, and says to set `LLM_MODEL` to another account-enabled model if it keeps happening. Its "Test page says the audio connection failed?" entry adds that Firefox doesn't offer loopback addresses, so the localhost-only config can't reach it: use Chrome, or in `about:config` set `media.peerconnection.ice.loopback` to `true`, and `media.peerconnection.ice.no_host` to `false` if it's on.

- On a page whose eighth or later image is the only one whose caption names the subject, that image comes first.
- Without a subject, or when nothing matches, the main image stays first and the order matches today's.
- The tool schema lists `url` and an optional `subject`, and a call with only `url` still works.
- `tests/test_agent.py` shows the session LLM options with a 5-second timeout and 3 retries.
- The live picture turn in `tests/test_agent_live.py` checks that `page_images` was called with a non-empty `subject`.

## page

Replace the in-chat card with one popup. It opens when the agent's description starts, paired with the same rules as the card: the first agent reply that starts after the images arrive and isn't a "One sec" filler, dropped by a new caller turn. It shows `images[0]` large, up to about 60% of the viewport height, letterboxed rather than cropped, with the agent's description streaming beneath it, a link naming the page's site (as the card does today, "Image from en.wikipedia.org") and a Close button. The reply also stays in the conversation as a normal agent turn. The thumbnail list under the `page_images` tool entry is removed. The raw result stays in its details, and the "No images found" line stays. Update the README sentence that describes the card.

When `room.connect` fails with the peer-connection error that `web/index.html` matches with `/pc connection/i`, and the browser is Firefox, the error names Firefox and suggests Chrome, or setting `media.peerconnection.ice.loopback` to `true` in `about:config`, instead of restarting LiveKit. Other browsers keep today's message.

- After an image lookup and the agent's reply, the popup shows `images[0]` with the reply text, and no thumbnails appear in the conversation.
- A "One sec" filler neither opens the popup nor becomes its description.
- The popup closes when any tool starts, on Close, on Escape, on session end, and when its image fails to load. A new image lookup's reply replaces it.
- A reply with no tool call leaves the popup open and unchanged.
- Opening doesn't move focus, and screen readers hear one short announcement naming the site. Close returns focus to the message box.
- The popup covers neither the agent state in the header nor the prompts and message box. The page has no sideways scroll at 375 px in light or dark, and no axe violations.
- The popup doesn't jump when its image loads, and it doesn't animate under reduced motion.
- In Firefox, a failed audio connection names Firefox and suggests Chrome or the loopback setting, not a restart. In Chrome the message is unchanged.

## After merge

- In Chrome at http://localhost:8090, ask "Find me a photo of young Joe Biden". A matching photo opens in the popup, larger than the old card, with the description streaming under it.
- Then ask "What's the weather in San Francisco?" The popup closes as soon as the search starts.
- In Firefox, if **Start session** can't open the audio connection, the error names Firefox and suggests Chrome.
- With VoiceOver on, the popup's opening is announced once, Close is reachable with Tab, and Escape closes it.
- `.venv/bin/python -m pytest -q tests/test_agent_live.py` passes with an AssemblyAI key. A skip means the live path is unverified.
