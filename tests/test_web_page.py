from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "web" / "index.html").read_text()


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found = []

    def handle_starttag(self, tag, attrs):
        self.found.append((tag, dict(attrs)))


def elements():
    parser = Elements()
    parser.feed(PAGE)
    return parser.found


def by_id(element_id):
    return next(
        (tag, attrs) for tag, attrs in elements() if attrs.get("id") == element_id
    )


def test_no_suggestion_buttons_remain():
    assert not any("data-prompt" in attrs for _, attrs in elements())
    assert ".prompt" not in PAGE
    assert "prompts" not in PAGE
    assert "example buttons" not in (ROOT / "README.md").read_text()


def test_message_box_says_you_can_speak_or_type():
    _, attrs = by_id("message")
    assert attrs["placeholder"] == "Speak or type a question"


def test_owl_is_hidden_from_screen_readers_and_the_state_word_is_text():
    assert by_id("figure")[1]["aria-hidden"] == "true"
    assert by_id("state-word")[0] == "p"


def test_jump_to_latest_is_a_button_above_the_message_box():
    tags = [(tag, attrs.get("id")) for tag, attrs in elements()]
    assert ("button", "jump") in tags
    assert tags.index(("button", "jump")) < tags.index(("input", "message"))
