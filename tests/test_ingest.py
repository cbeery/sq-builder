"""Paste-cleaner regression tests against real browser copies.

The fixtures are genuine junk pasted out of ESPN, the Washington Post and
Boulder Reporting Lab. These are the tests that matter: the cleaner is
heuristic, so it is exactly where a regression will show up.
"""

import pytest

from sq.ingest import clean, profile_for, slugify, to_markdown

FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"

CASES = [
    pytest.param(
        "espn", "https://www.espn.com/x",
        {"title": "The Longest Afternoon at Kestrel Park",
         "author": "Dana Whitfield", "date": "2026-09-09",
         "dek": "A twenty-year-old infielder, a season handed to him, and "
                "a club standing well back."},
        {"figures": 3, "dropcaps": 3, "recirc": 1}, id="espn"),
    pytest.param(
        "wapo", "https://www.washingtonpost.com/x",
        {"title": "The last switchboard operators are retiring",
         "author": "Nadia Okonkwo", "date": "2026-07-17",
         "dek": "A job that once employed thousands now has fewer than "
                "forty people left in it, and the last of them are going."},
        {"figures": 3, "dropcaps": 1, "recirc": 1}, id="wapo"),
    pytest.param(
        "local", "https://boulderreportinglab.org/x",
        {"title": "Before the Kestrel Diner, there was Whitlow's Garage",
         "author": "Ellen Farriday", "date": "2026-05-05"},
        {"figures": 3, "dropcaps": 1, "recirc": 0}, id="local"),
]


def render(name, url, meta):
    raw = (FIXTURES / f"{name}.txt").read_text(encoding="utf-8")
    meta = dict(meta, url=url)
    return to_markdown(clean(raw, profile_for(url), meta), meta)


@pytest.mark.parametrize("name,url,meta,want", CASES)
def test_cleaner_shape(name, url, meta, want):
    lines = render(name, url, meta).splitlines()
    got = {
        "figures": sum(1 for l in lines if l.startswith("![")),
        "dropcaps": sum(1 for l in lines if l.startswith("@@ ")),
        "recirc": sum(1 for l in lines if "recirculation module" in l),
    }
    assert got == want


@pytest.mark.parametrize("name,url,meta,want", CASES)
def test_bio_is_always_todo(name, url, meta, want):
    """Bios are written by hand, every time — never scraped, never
    inferred. The cleaner must not pretend otherwise."""
    assert "bio: # TODO" in render(name, url, meta)


@pytest.mark.parametrize("name,url,meta,want", CASES)
def test_no_qr_codes(name, url, meta, want):
    """Discontinued from Fall 2026. The url stays in frontmatter."""
    out = render(name, url, meta).lower()
    assert "qr" not in out
    assert "url:" in out


def test_publication_inferred_from_host():
    assert profile_for("https://www.espn.com/x")["publication"] == "ESPN"
    assert profile_for("https://washingtonpost.com/x")["publication"] == \
        "The Washington Post"
    assert profile_for("https://example.com/x")["publication"] == ""


@pytest.mark.parametrize("title,want", [
    ("The Longest Afternoon at Kestrel Park", "the-longest-afternoon-at"),
    ("The death of the stick shift", "the-death-of-the"),
    ("", "article"),
    ("Café — naïve", "cafe-naive"),
])
def test_slugify(title, want):
    assert slugify(title) == want


# --- clipboard encoding ----------------------------------------------------

def test_decode_paste_repairs_mac_roman_bytes():
    """macOS pbpaste does not reliably hand back UTF-8. A copy out of the
    browser can arrive as Mac OS Roman, where 0x8E is an e-acute. Reading
    that as UTF-8 raises — and reading it with errors="replace" would put
    a replacement character into a printed magazine."""
    from sq.ingest import decode_paste
    assert decode_paste(b"the second Pok\x8emon pack") == \
        "the second Pokémon pack"


def test_decode_paste_leaves_real_utf8_alone():
    from sq.ingest import decode_paste
    for s in ("café “quoted” — dash…", "plain ascii", "Pokémon"):
        assert decode_paste(s.encode("utf-8")) == s


def test_decode_paste_handles_a_mixed_stream():
    """Valid sequences decode as UTF-8; only the bytes that cannot are
    reinterpreted, so a mixed paste survives either way."""
    from sq.ingest import decode_paste
    raw = "curly ’quote’ ".encode("utf-8") + b"and Pok\x8emon"
    assert decode_paste(raw) == "curly ’quote’ and Pokémon"


# --- small-caps section openers ---------------------------------------------

@pytest.mark.parametrize("line,want", [
    # the two that were missed: a year, and a run ending on a full stop
    ("BACK IN 1964, a few months before she gave birth",
     "BACK IN 1964,"),
    ("MARCUS HALLOWAY IS 20. Bat on his shoulder, a crooked smile",
     "MARCUS HALLOWAY IS 20."),
    # the ones that always worked
    ("MARCUS HALLOWAY, STILL in his warmups, leans on",
     "MARCUS HALLOWAY, STILL"),
    ("BY THE TIME Halloway turned 20, his mother",
     "BY THE TIME"),
    ("A CONTINENT APART, separated by years and by talent",
     "A CONTINENT APART,"),
])
def test_leadin_is_detected(line, want):
    """ESPN opens each section with a small-caps run. The run may contain a
    year and may end on a full stop — both of those used to defeat it, so
    the paragraph silently lost its drop cap."""
    from sq.ingest import LEADIN
    m = LEADIN.match(line)
    assert m is not None, "lead-in not detected"
    assert m.group(1) == want


@pytest.mark.parametrize("line", [
    "A TV station called Konnor a Phenom when he was 15",
    "But Griffin is 19.",
    "He swipes up. Another video. Swipes again.",
    "Marcus Halloway is 20. Standing in the tunnel under",
])
def test_ordinary_prose_is_not_mistaken_for_a_leadin(line):
    """Three words minimum, all of them capitalised — otherwise an opener
    like 'A TV station called...' gets a drop cap it never asked for."""
    from sq.ingest import LEADIN
    assert LEADIN.match(line) is None


def test_marked_leadin_round_trips_to_a_dropcap():
    from sq.content import parse_blocks
    from sq.ingest import mark_leadin
    marked = mark_leadin("BACK IN 1964, a few months before she gave birth")
    block = parse_blocks(f"@@ {marked}")[0]
    assert block["dropcap"] is True
    assert block["text"].startswith("{sc}BACK IN 1964,{/sc}")
