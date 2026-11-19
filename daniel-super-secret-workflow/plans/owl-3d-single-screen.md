# 3D owl, new theme and a one-screen page

## Overview

The test page (`web/index.html`) draws its owl from hand-made ASCII frames in the header (`OWL`, `EYES`, `SCENES`, `drawScene`), puts three suggestion buttons above the message box (`.prompts`), and snaps the conversation to the bottom on every entry (`follow`). At 1280×800 the header and suggestions leave the popup image only 262 px.

After this change the owl is real 3D ASCII: a small model rendered and shaded every frame, so it turns, breathes, blinks and moves its head with depth. Each scene keeps its meaning through pose, motion and a prop in the same style, and the beak still follows the agent's voice. A new theme, chosen with the installed design skills, is built around the owl in light and dark. The page fits one screen. On a wide window the owl and agent state get a column beside the conversation, and on a phone a compact header. Only the conversation scrolls, smoothly, without pulling you away from what you scrolled up to read. The suggestions are gone.

The agent, its events, the popup's rules, announcements and the Firefox message are unchanged. Callers are blind or have low vision, so the Atkinson Hyperlegible fonts and WCAG AA contrast stay, and reduced motion gets a still owl. At high zoom or on very short screens the page still scrolls as a whole, since one fixed screen would hide content.

One worker. The owl, theme and layout share `web/index.html` and the same sizing and color decisions.

Read `~/.agents/skills/frontend-design/SKILL.md`, `~/.agents/skills/impeccable/SKILL.md`, `~/.agents/skills/emil-design-eng/SKILL.md` and `~/.agents/skills/animate/SKILL.md` (on the developer's machine, outside the repo) before choosing the theme and the motion.

- The owl is rendered from a 3D model each frame: as its head turns, shading and outline change with the angle.
- Each of today's scenes has its own pose or motion, and the four tool scenes each show a prop. While the agent speaks, the beak opens with its audio level.
- The figure stays `aria-hidden`; the state word stays its text equivalent.
- The owl stops drawing in a hidden tab, keeps a fixed box size while fonts load, and renders a frame in under 4 ms on a laptop.
- Under reduced motion the owl holds one still pose per scene and scrolling isn't animated.
- Text meets 4.5:1, and controls and focus outlines 3:1, in light and dark. The four tool colors stay distinct. axe reports no violations in either theme.
- At 1280×800, 1440×900 and 375×667, on the start screen, in a long conversation and with the popup open, the page never scrolls, only the conversation. Agent state, session controls and message box stay on screen, with no sideways scroll at 375 px.
- At 1280×800 the popup image is at least 288 px tall and covers neither the agent state nor the message box.
- At 400% zoom, or under 32rem tall, the page scrolls as a whole and nothing is cut off.
- No suggestion buttons remain, in markup, styles or handlers. The message box placeholder says you can speak or type. The README no longer mentions example buttons.
- At the end of the conversation, new turns and streaming text scroll into view smoothly, without jumps.
- Scrolled up, new content doesn't move you. A Jump to latest button appears above the message box, is reachable with Tab, scrolls to the end, and hides there or when you scroll down by hand.
- Scrolling past either end of the conversation doesn't bounce the page.
- Session controls stay in one place before, during and after a session.

## After merge

- In Chrome at http://localhost:8090 in a live session, the owl's beak moves with the agent's voice, and the owl changes pose and prop when Search, Fetch, Decisions and Images run.
- On a real phone and a 13-inch laptop screen, a full session fits one screen without scrolling the page.
- With VoiceOver on, the owl isn't read aloud, and Jump to latest is reachable and named.
