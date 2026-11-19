import json
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from livekit.agents import RunContext, ToolError, llm

import page_images
from page_images import MAX_BYTES, MAX_IMAGES, MAX_TEXT_CHARS, find_images

ARTICLE = """\
<!doctype html>
<html><head>
<title>Golden Gate Bridge | Example Travel</title>
<meta property="og:image" content="/photos/1200px-bridge-from-marin.jpg">
<meta property="og:image:alt" content="The bridge's red towers above the fog">
<script type="application/ld+json">
{"@type": "Article", "image": {"@type": "ImageObject",
 "url": "https://example.org/photos/bridge-from-marin.jpg",
 "caption": "The bridge seen from the Marin Headlands at sunrise"}}
</script>
</head><body>
<header><img src="/static/site-logo.png" alt="Example Travel"></header>
<img src="/static/spacer.gif" alt="">
<main>
<h1>Golden Gate Bridge</h1>
<figure>
  <img src="/photos/towers.jpg" alt="Workers on a tower" width="800" height="600">
  <figcaption>Riveters on the south tower in 1935.</figcaption>
</figure>
<h2>Fog</h2>
<p>Summer fog pours through the strait most afternoons.</p>
<figure>
  <img src="/photos/fog.jpg">
  <figcaption>Fog rolling in under the deck.</figcaption>
</figure>
<h2>Visiting</h2>
<p>The east sidewalk is open to walkers from dawn to dusk.</p>
<img src="/photos/walkway.jpg">
<p>Parking at the welcome center fills early on weekends.</p>
<figure>
  <img src="/photos/600px-bridge-from-marin.jpg" alt="" width="600" height="400">
</figure>
</main>
<img src="https://stats.example.net/collect?id=42" width="1" height="1">
</body></html>
"""


def html_page(body, status=200):
    return httpx.Response(
        status, headers={"content-type": "text/html; charset=utf-8"}, text=body
    )


class Site:
    """An httpx transport that serves pages by URL and records every request."""

    def __init__(self, pages):
        self.pages = pages
        self.requested = []

    def __call__(self, request):
        self.requested.append(str(request.url))
        page = self.pages[str(request.url)]
        return page(request) if callable(page) else page

    @property
    def transport(self):
        return httpx.MockTransport(self)


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    addresses = {
        "example.org": ["93.184.215.14"],
        "localhost": ["127.0.0.1", "::1"],
        "intranet.example.org": ["10.1.2.3"],
    }

    async def resolve(host):
        if host not in addresses:
            raise socket.gaierror(f"unknown host {host}")
        return addresses[host]

    monkeypatch.setattr(page_images, "_resolve", resolve)


async def test_article_lists_meaningful_images_main_image_first():
    site = Site({"https://example.org/bridge": html_page(ARTICLE)})

    result = await find_images("https://example.org/bridge", site.transport)

    assert result["page"] == "https://example.org/bridge"
    assert result["title"] == "Golden Gate Bridge | Example Travel"
    assert result["skipped"] == 3  # logo, spacer and tracking pixel
    assert result["note"] is None
    main, towers, fog, walkway = result["images"]
    assert main == {
        "n": 1,
        "src": "https://example.org/photos/600px-bridge-from-marin.jpg",
        "alt": "The bridge's red towers above the fog",
        "caption": "The bridge seen from the Marin Headlands at sunrise",
        "context": main["context"],
    }
    assert towers["n"] == 2
    assert towers["src"] == "https://example.org/photos/towers.jpg"
    assert towers["alt"] == "Workers on a tower"
    assert towers["caption"] == "Riveters on the south tower in 1935."
    assert towers["context"].startswith("Golden Gate Bridge: ")
    assert fog["alt"] is None
    assert fog["caption"] == "Fog rolling in under the deck."
    assert fog["context"].startswith("Fog: Summer fog pours through the strait")


async def test_image_without_alt_or_caption_keeps_its_surrounding_text():
    site = Site({"https://example.org/bridge": html_page(ARTICLE)})

    result = await find_images("https://example.org/bridge", site.transport)

    walkway = result["images"][3]
    assert walkway["src"] == "https://example.org/photos/walkway.jpg"
    assert walkway["alt"] is None
    assert walkway["caption"] is None
    assert "east sidewalk is open to walkers" in walkway["context"]
    assert "welcome center fills early" in walkway["context"]


async def test_without_og_image_the_first_large_image_in_main_leads():
    page = """<body><img src="/a.jpg" alt="Banner ad" width="300" height="250">
    <article><img src="/b.jpg" alt="Thumbnail" width="120" height="90">
    <img src="/c.jpg" alt="Hero" width="1024" height="576"></article></body>"""
    site = Site({"https://example.org/": html_page(page)})

    result = await find_images("https://example.org/", site.transport)

    assert [image["alt"] for image in result["images"]] == [
        "Hero",
        "Banner ad",
        "Thumbnail",
    ]


async def test_text_is_clipped_and_the_list_stops_at_eight():
    long_alt = "A very long description of the bridge " * 20
    figures = "".join(
        f'<h2>{long_alt}</h2><p>{long_alt}</p><figure><img src="/photo-{n}.jpg" '
        f'alt="{long_alt}"><figcaption>{long_alt}</figcaption></figure>'
        for n in range(MAX_IMAGES + 4)
    )
    site = Site({"https://example.org/": html_page(f"<body>{figures}</body>")})

    result = await find_images("https://example.org/", site.transport)

    assert len(result["images"]) == MAX_IMAGES
    assert [image["n"] for image in result["images"]] == list(range(1, 9))
    for image in result["images"]:
        for field in ("alt", "caption", "context"):
            assert len(image[field]) <= MAX_TEXT_CHARS
    assert result["images"][0]["alt"].endswith("…")


async def test_page_without_described_images_says_so():
    page = '<body><img src="/icons/search.svg" alt=""><img src="/photo.jpg"></body>'
    site = Site({"https://example.org/": html_page(page)})

    result = await find_images("https://example.org/", site.transport)

    assert result["skipped"] == 1
    assert len(result["images"]) == 1
    assert result["note"]


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://127.0.0.1:8000/",
        "http://10.0.0.5/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",
        "https://intranet.example.org/",
        "file:///etc/passwd",
    ],
)
async def test_private_and_local_addresses_are_refused(url):
    site = Site({})

    with pytest.raises(ToolError):
        await find_images(url, site.transport)
    assert site.requested == []


async def test_redirect_to_a_private_address_is_refused_before_it_is_requested():
    site = Site(
        {
            "https://example.org/go": httpx.Response(
                302, headers={"location": "http://10.0.0.5/admin"}
            )
        }
    )

    with pytest.raises(ToolError, match="private or local network"):
        await find_images("https://example.org/go", site.transport)
    assert site.requested == ["https://example.org/go"]


async def test_redirects_are_followed_up_to_three_times():
    # /0 redirects to /1, and so on up to /4.
    site = Site(
        {
            f"https://example.org/{n}": lambda request, n=n: httpx.Response(
                301, headers={"location": f"/{n + 1}"}
            )
            for n in range(4)
        }
    )
    site.pages["https://example.org/4"] = html_page('<img src="/a.jpg" alt="A">')

    result = await find_images("https://example.org/1", site.transport)
    assert result["page"] == "https://example.org/4"

    site.requested.clear()
    with pytest.raises(ToolError, match="redirected too many times"):
        await find_images("https://example.org/0", site.transport)
    assert site.requested == [f"https://example.org/{n}" for n in range(4)]


def timeout(request):
    raise httpx.ReadTimeout("timed out", request=request)


@pytest.mark.parametrize(
    "response, reason",
    [
        (html_page("x" * (MAX_BYTES + 1)), "too large"),
        (timeout, "too long to respond"),
        (html_page("Forbidden", status=403), "error 403"),
        (
            httpx.Response(200, headers={"content-type": "application/pdf"}),
            "isn't a web page",
        ),
    ],
)
async def test_failures_raise_a_reason_to_say_aloud(response, reason):
    site = Site({"https://example.org/": response})

    with pytest.raises(ToolError, match=reason):
        await find_images("https://example.org/", site.transport)


async def test_unknown_host_is_reported():
    with pytest.raises(ToolError, match="couldn't find that website"):
        await find_images("https://no-such-host.example/", Site({}).transport)


async def test_direct_image_url_returns_that_image_with_its_file_name():
    url = "https://example.org/media/Golden_Gate_Bridge_at_sunset.jpg"
    site = Site(
        {url: httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"")}
    )

    result = await find_images(url, site.transport)

    assert result["images"] == [
        {
            "n": 1,
            "src": url,
            "alt": None,
            "caption": None,
            "context": "Golden Gate Bridge at sunset",
        }
    ]
    assert result["note"]
    assert result["skipped"] == 0


async def test_tool_takes_one_url_and_returns_json(monkeypatch):
    schema = llm.utils.build_legacy_openai_schema(page_images.page_images)
    assert schema["function"]["name"] == "page_images"
    assert list(schema["function"]["parameters"]["properties"]) == ["url"]

    async def fake_find_images(url):
        return {"page": url, "images": []}

    monkeypatch.setattr(page_images, "find_images", fake_find_images)
    ctx = RunContext(
        session=Mock(wait_for_idle=AsyncMock()),
        speech_handle=SimpleNamespace(num_steps=1),
        function_call=Mock(),
    )
    output = await page_images.page_images(ctx, "https://example.org/")
    assert json.loads(output) == {"page": "https://example.org/", "images": []}
