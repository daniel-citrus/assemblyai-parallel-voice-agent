"""List a web page's meaningful images with the page's own words about each one.

The AssemblyAI gateway accepts only text, and Parallel Fetch drops images and
their alt text, so this tool reads the page's HTML itself. A description is only
as good as the alt text, captions and surrounding text the page provides.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import socket
from html.parser import HTMLParser
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from livekit.agents import RunContext, ToolError, function_tool

from voice_mcp import acknowledge_slow_lookup

USER_AGENT = (
    "assemblyai-parallel-voice-agent/0.1 (voice assistant that reads image "
    "descriptions aloud; +https://github.com/hsingh-aai/assemblyai-parallel-voice-agent)"
)
TIMEOUT_SECONDS = 10
MAX_BYTES = 3 * 1024 * 1024
MAX_REDIRECTS = 3
MAX_IMAGES = 8
MAX_TEXT_CHARS = 300
# A declared width or height below this marks an icon or tracking pixel.
MIN_PIXELS = 64
# Without an og:image, the first image this large in main or article leads.
MAIN_IMAGE_PIXELS = 200
DECORATIVE_WORDS = re.compile(
    r"\b(?:icons?|logos?|spacer|tracking|tracker|beacon|sprites?|favicon)\b"
)
DECORATIVE_FILES = {"pixel", "blank", "clear", "transparent", "1x1"}
# Subject words that don't tell one picture from another.
FILLER_WORDS = set(
    "a an the of in on at and with to for from main photo picture image".split()
)
HTML_TYPES = {"text/html", "application/xhtml+xml"}
# Text inside these never describes an image; sup holds footnote markers.
SILENT_TAGS = {"style", "noscript", "template", "svg", "nav", "sup"}
META_KEYS = {
    "og:image",
    "og:image:alt",
    "twitter:image:alt",
    "og:description",
    "description",
}


@function_tool
async def page_images(ctx: RunContext, url: str, subject: str | None = None) -> str:
    """List the meaningful images on a public web page, with the page's own
    words about each: alt text, caption and surrounding text. The image whose
    words best match the subject comes first, otherwise the page's main image.
    These words are all you know about an image; you cannot see it.

    Args:
        url: The full http or https address of the page, or of an image file.
        subject: What the caller wants pictured, in a few words, such as
            "young Joe Biden". Leave it empty to get the page's main image first.
    """
    async with acknowledge_slow_lookup(ctx, "page_images"):
        return json.dumps(await find_images(url, subject=subject))


async def find_images(
    url: str,
    transport: httpx.AsyncBaseTransport | None = None,
    subject: str | None = None,
) -> dict[str, Any]:
    try:
        target = httpx.URL(url.strip())
    except httpx.InvalidURL as e:
        raise ToolError("That doesn't look like a web address.") from e
    async with httpx.AsyncClient(
        transport=transport,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
    ) as client:
        try:
            for _ in range(MAX_REDIRECTS + 1):
                await _check_public(target)
                async with client.stream("GET", target) as response:
                    if response.next_request is not None:
                        target = response.next_request.url
                        continue
                    return await _read_images(response, subject)
        except httpx.TimeoutException as e:
            raise ToolError("The page took too long to respond.") from e
        except httpx.HTTPError as e:
            raise ToolError("I couldn't connect to that website.") from e
    raise ToolError("The page redirected too many times.")


async def _resolve(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, None, type=socket.SOCK_STREAM
    )
    return [info[4][0] for info in infos]


async def _check_public(url: httpx.URL) -> None:
    """Refuse anything but http or https to a public address, before connecting."""
    if url.scheme not in ("http", "https") or not url.host:
        raise ToolError(
            "I can only open public web addresses that start with http or https."
        )
    try:
        addresses = [ipaddress.ip_address(url.host)]
    except ValueError:
        try:
            addresses = [ipaddress.ip_address(a) for a in await _resolve(url.host)]
        except OSError as e:
            raise ToolError("I couldn't find that website.") from e
    for address in addresses:
        address = getattr(address, "ipv4_mapped", None) or address
        if not address.is_global or address.is_multicast:
            raise ToolError(
                "That address is on a private or local network, so I won't open it."
            )


async def _read_images(response: httpx.Response, subject: str | None) -> dict[str, Any]:
    if response.status_code >= 400:
        raise ToolError(
            f"The site wouldn't give me that page. It answered with error "
            f"{response.status_code}."
        )
    content_type = response.headers.get("content-type", "").split(";")[0]
    content_type = content_type.strip().lower()
    if content_type.startswith("image/"):
        return _direct_image(str(response.url))
    if content_type not in HTML_TYPES:
        raise ToolError("That link isn't a web page or an image.")
    body = bytearray()
    async for chunk in response.aiter_bytes():
        body += chunk
        if len(body) > MAX_BYTES:
            raise ToolError("That page is too large to read, over three megabytes.")
    return extract_images(
        body.decode(response.encoding or "utf-8", errors="replace"),
        str(response.url),
        subject,
    )


def _direct_image(url: str) -> dict[str, Any]:
    image = {
        "n": 1,
        "src": url,
        "alt": None,
        "caption": None,
        "context": _clip(_words(_file_stem(url))),
    }
    return {
        "page": url,
        "title": None,
        "images": [image],
        "skipped": 0,
        "note": "This link is an image file with no page text about it, "
        "only its file name.",
    }


def extract_images(
    html: str, page_url: str, subject: str | None = None
) -> dict[str, Any]:
    """Return the `page_images` result for an HTML document."""
    parser = _PageParser(page_url)
    parser.feed(html)
    parser.close()
    text = " ".join(parser.text)
    ld_captions = _json_ld_captions(parser.json_ld, parser.base)
    og_image = _image_source({"src": parser.meta.get("og:image")}, parser.base)
    if og_image and _marks_decorative(og_image):
        og_image = None
    og_key = og_image and _image_key(og_image)

    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    skipped = 0
    for image in parser.images:
        src, attrs = image["src"], image["attrs"]
        if src in seen:
            continue
        seen.add(src)
        key = _image_key(src)
        caption = image["caption"] or ld_captions.get(key)
        is_og_image = key == og_key
        if not is_og_image and _is_decorative(attrs, src, caption):
            skipped += 1
            continue
        kept.append(
            {
                "src": src,
                "alt": _alt(attrs),
                "caption": caption,
                "context": _context(image, text),
                "main": is_og_image
                if og_image
                else image["in_main"] and _declared_size(attrs) >= MAIN_IMAGE_PIXELS,
            }
        )

    main = next((image for image in kept if image["main"]), None)
    if main is not None:
        kept.remove(main)
    elif og_image:
        # The og:image is often a crop that the page itself doesn't show.
        description = parser.meta.get("og:description") or parser.meta.get(
            "description"
        )
        main = {
            "src": og_image,
            "alt": None,
            "caption": ld_captions.get(og_key),
            "context": ": ".join(filter(None, (parser.title, description))),
        }
    if main is not None:
        if og_image:
            main["alt"] = (
                main["alt"]
                or parser.meta.get("og:image:alt")
                or parser.meta.get("twitter:image:alt")
            )
        kept.insert(0, main)
    if subject:
        wanted = _match_words(subject) - FILLER_WORDS
        # The sort is stable, so ties keep page order with the main image first.
        kept.sort(key=lambda image: _relevance(image, wanted), reverse=True)

    images = [
        {
            "n": n,
            "src": image["src"],
            "alt": _clip(image["alt"]),
            "caption": _clip(image["caption"]),
            "context": _clip(image["context"]),
        }
        for n, image in enumerate(kept[:MAX_IMAGES], 1)
    ]
    note = None
    if not images:
        note = "The page has no meaningful images."
    elif not any(image["alt"] or image["caption"] for image in images):
        note = "No image here has alt text or a caption, only the text around it."
    return {
        "page": page_url,
        "title": _clip(parser.title),
        "images": images,
        "skipped": skipped,
        "note": note,
    }


class _PageParser(HTMLParser):
    def __init__(self, page_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base = page_url
        self.title = ""
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        self.images: list[dict[str, Any]] = []
        # Page text outside captions, with images placed by character position.
        self.text: list[str] = []
        self._text_length = 0
        self._heading: str | None = None
        self._section_start = 0
        self._heading_parts: list[str] | None = None
        self._figures: list[dict[str, Any]] = []
        self._caption_depth = 0
        self._main_depth = 0
        self._silent_depth = 0
        self._in_title = False
        self._json_ld: list[str] | None = None
        self._base_set = False

    def handle_starttag(
        self, tag: str, attr_list: list[tuple[str, str | None]]
    ) -> None:
        attrs = dict(attr_list)
        if tag == "img":
            self._add_image(attrs)
        elif tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            if key in META_KEYS and attrs.get("content"):
                self.meta.setdefault(key, attrs["content"])
        elif tag == "base" and attrs.get("href") and not self._base_set:
            self.base = urljoin(self.base, attrs["href"])
            self._base_set = True
        elif tag == "script":
            if (attrs.get("type") or "").lower() == "application/ld+json":
                self._json_ld = []
            else:
                self._silent_depth += 1
        elif tag in SILENT_TAGS:
            self._silent_depth += 1
        elif tag == "title" and not self._silent_depth:
            self._in_title = True
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._heading_parts = []
        elif tag == "figure":
            self._figures.append({"caption": [], "images": []})
        elif tag == "figcaption" and self._figures:
            self._caption_depth += 1
        elif tag in ("main", "article"):
            self._main_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            if self._json_ld is not None:
                self.json_ld.append("".join(self._json_ld))
                self._json_ld = None
            else:
                self._silent_depth = max(0, self._silent_depth - 1)
        elif tag in SILENT_TAGS:
            self._silent_depth = max(0, self._silent_depth - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            if self._heading_parts:
                self._heading = " ".join(self._heading_parts)
                self._section_start = self._text_length
            self._heading_parts = None
        elif tag == "figure" and self._figures:
            self._caption_depth = 0
            figure = self._figures.pop()
            caption = " ".join(figure["caption"]) or None
            for image in figure["images"]:
                image["caption"] = caption
        elif tag == "figcaption":
            self._caption_depth = max(0, self._caption_depth - 1)
        elif tag in ("main", "article"):
            self._main_depth = max(0, self._main_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._json_ld is not None:
            self._json_ld.append(data)
            return
        text = " ".join(data.split())
        if not text or self._silent_depth:
            return
        if self._in_title:
            self.title = f"{self.title} {text}".strip()
        elif self._caption_depth:
            _add_text(self._figures[-1]["caption"], text)
        else:
            if self._heading_parts is not None:
                _add_text(self._heading_parts, text)
            self._text_length += _add_text(self.text, text)

    def _add_image(self, attrs: dict[str, str | None]) -> None:
        src = _image_source(attrs, self.base)
        if src is None:
            return
        image = {
            "src": src,
            "attrs": attrs,
            "caption": None,
            "heading": self._heading,
            "section_start": self._section_start,
            "position": self._text_length,
            "in_main": self._main_depth > 0,
        }
        self.images.append(image)
        if self._figures:
            self._figures[-1]["images"].append(image)


def _add_text(parts: list[str], text: str) -> int:
    """Append text, keeping leading punctuation on the word before it.

    Returns how much longer `" ".join(parts)` plus a trailing space became.
    """
    if parts and text[0] in ",.;:!?)":
        parts[-1] += text
        return len(text)
    parts.append(text)
    return len(text) + 1


def _image_source(attrs: dict[str, str | None], base: str) -> str | None:
    """Prefer the real image over a lazy-loading placeholder."""
    candidates = [attrs.get("src"), attrs.get("data-src")]
    for srcset in (attrs.get("srcset"), attrs.get("data-srcset")):
        candidates += (srcset or "").split()[:1]
    for candidate in candidates:
        if candidate and not candidate.strip().startswith("data:"):
            src = urljoin(base, candidate.strip())
            if src.startswith(("http://", "https://")):
                return src
    return None


def _is_decorative(attrs: dict[str, str | None], src: str, caption: str | None) -> bool:
    if "alt" in attrs and not (attrs["alt"] or "").strip() and not caption:
        return True
    if (attrs.get("role") or "").lower() in ("presentation", "none"):
        return True
    if (attrs.get("aria-hidden") or "").lower() == "true":
        return True
    for size in (_pixels(attrs.get("width")), _pixels(attrs.get("height"))):
        if size is not None and size < MIN_PIXELS:
            return True
    names = _words(f"{attrs.get('class') or ''} {attrs.get('id') or ''}").lower()
    return _marks_decorative(src) or bool(DECORATIVE_WORDS.search(names))


def _marks_decorative(src: str) -> bool:
    stem = _file_stem(src)
    return stem.lower() in DECORATIVE_FILES or bool(
        DECORATIVE_WORDS.search(_words(stem).lower())
    )


def _pixels(value: str | None) -> int | None:
    match = re.fullmatch(r"\s*(\d+)\s*(?:px)?\s*", value or "")
    return int(match.group(1)) if match else None


def _declared_size(attrs: dict[str, str | None]) -> int:
    sizes = [_pixels(attrs.get("width")), _pixels(attrs.get("height"))]
    return max((size for size in sizes if size is not None), default=0)


def _alt(attrs: dict[str, str | None]) -> str | None:
    parts: list[str] = []
    for key in ("alt", "aria-label", "title"):
        value = " ".join((attrs.get(key) or "").split())
        if value and value not in parts:
            parts.append(value)
    return "; ".join(parts) or None


def _context(image: dict[str, Any], text: str) -> str | None:
    """The nearest heading, a little of its section before the image, more after."""
    position, heading = image["position"], image["heading"]
    start = max(image["section_start"], position - 100)
    before = text[start:position]
    if start > image["section_start"]:
        before = before.partition(" ")[2]
    after = text[position : position + MAX_TEXT_CHARS]
    context = " ".join(part for part in (before.strip(), after.strip()) if part)
    if heading:
        context = f"{heading}: {context}" if context else heading
    return context or None


def _relevance(image: dict[str, Any], wanted: set[str]) -> tuple[int, int]:
    """Count subject words in the alt text or caption, then the rest in the
    context or file name, which say less about the image itself."""
    described = _match_words(f"{image['alt'] or ''} {image['caption'] or ''}")
    nearby = _match_words(
        f"{image['context'] or ''} {_words(_file_stem(image['src']))}"
    )
    return len(wanted & described), len(wanted & (nearby - described))


def _match_words(text: str) -> set[str]:
    """Lowercase words without a plural "s", so "towers" matches "tower"."""
    words = re.findall(r"[^\W_]+", text.lower())
    return {
        word[:-1] if len(word) > 3 and word.endswith("s") else word for word in words
    }


def _json_ld_captions(scripts: list[str], base: str) -> dict[str, str]:
    """Map each JSON-LD image to its caption or description."""
    captions: dict[str, str] = {}

    def visit(node: Any, is_image: bool) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item, is_image)
        elif isinstance(node, dict):
            types = node.get("@type")
            if is_image or "ImageObject" in (
                types if isinstance(types, list) else [types]
            ):
                src = node.get("contentUrl") or node.get("url")
                text = node.get("caption") or node.get("description")
                if isinstance(src, str) and isinstance(text, str):
                    captions.setdefault(_image_key(urljoin(base, src)), text)
            for key, value in node.items():
                visit(value, key in ("image", "primaryImageOfPage"))

    for script in scripts:
        try:
            visit(json.loads(script), False)
        except ValueError:
            continue
    return captions


def _image_key(src: str) -> str:
    """Match one image across sizes, such as an og:image and its page thumbnail."""
    name = PurePosixPath(urlsplit(src).path).name.lower()
    return re.sub(r"^\d+px-", "", name) if "." in name else src.split("?")[0]


def _file_stem(src: str) -> str:
    return unquote(PurePosixPath(urlsplit(src).path).stem)


def _words(name: str) -> str:
    """Split a file or class name into words, including camelCase ones."""
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    return " ".join(re.sub(r"[\W_]+", " ", name).split())


def _clip(text: str | None) -> str | None:
    text = " ".join((text or "").split())
    if len(text) <= MAX_TEXT_CHARS:
        return text or None
    cut = text[: MAX_TEXT_CHARS - 1].rsplit(" ", 1)[0] or text[: MAX_TEXT_CHARS - 1]
    return f"{cut}…"
