"""End-to-end render tests on a synthetic issue.

Layout doesn't get unit tests — preflight is the test for that. What these
cover is the contract between the pieces: that every dialect construct
survives the trip to PDF, that the page geometry lands where Mixam expects
it, and that padding to a multiple of 4 actually happens.
"""

import pytest
from PIL import Image
from pypdf import PdfReader

from sq.content import ContentError
from sq.render import build

ARTICLE = """---
title: A Title Here
dek: A dek here
author: A Person
publication: Somewhere
date: 2026-01-01
url: https://example.com/x
bio: A bio.
---

@@ Opening paragraph with *emphasis* and **strong** words. __BODY__

## A Subhead

Another paragraph.

***

> Something quotable.
> -- Someone

![A caption](images/plate.jpg){.full}

![Floated](images/plate.jpg){.right}

|+ A Table Title
| Year | League | Event |
|---|:---:|---:|
| 1994 | NHL | Rangers win it |
| 2015 | MLB | The bat flip |

Closing paragraph.
"""

ISSUE = """title: Stan Quarterly
abbr: SQ
issue: Test 2099
subtitle: Compiled by Curt, for Stan
colophon: All content reprinted without permission. Oh well.
mark:
  image: images/mark.png
cover:
  image: images/plate.jpg
  focus: center
back_cover:
  image: images/plate.jpg
  focus: center
__GEOMETRY__
articles:
  - articles/01-a.md
"""


@pytest.fixture
def issue_dir(tmp_path):
    def make(geometry="", body="Filler sentence. " * 40):
        d = tmp_path / "2099-test"
        (d / "articles").mkdir(parents=True, exist_ok=True)
        (d / "images").mkdir(exist_ok=True)
        Image.new("RGB", (2100, 3150), "grey").save(d / "images/plate.jpg")
        Image.new("RGBA", (600, 300), (255, 255, 255, 128)).save(
            d / "images/mark.png")
        (d / "issue.yaml").write_text(ISSUE.replace("__GEOMETRY__", geometry))
        (d / "articles/01-a.md").write_text(ARTICLE.replace("__BODY__", body))
        return d
    return make


def test_builds_a_valid_mixam_pdf(issue_dir, tmp_path):
    pdf = build(issue_dir(), tmp_path / "out")
    reader = PdfReader(str(pdf))
    page = reader.pages[0]

    assert len(reader.pages) % 4 == 0, "page count must be a multiple of 4"
    assert float(page.mediabox.width) == pytest.approx(499.68, abs=0.01)
    assert float(page.mediabox.height) == pytest.approx(755.28, abs=0.01)
    assert float(page.trimbox.width) == pytest.approx(481.68, abs=0.01)
    assert float(page.trimbox.height) == pytest.approx(737.28, abs=0.01)


def test_every_dialect_construct_reaches_the_page(issue_dir, tmp_path):
    pdf = build(issue_dir(), tmp_path / "out")
    text = "\n".join(p.extract_text() for p in PdfReader(str(pdf)).pages)
    for want in ["A Title Here", "A dek here", "A Subhead", "emphasis",
                 "strong", "Something quotable", "Someone", "A caption",
                 "Floated", "* * *", "A bio.",
                 "A Table Title", "League", "The bat flip"]:
        assert want in text, f"{want!r} missing from the PDF"


def test_padding_reaches_a_multiple_of_four(issue_dir, tmp_path):
    """Body length is varied so the natural page count lands differently;
    the result must always be padded up."""
    for words in (10, 300, 900):
        pdf = build(issue_dir(body="Word " * words), tmp_path / f"out{words}")
        n = len(PdfReader(str(pdf)).pages)
        assert n % 4 == 0, f"{words} words gave {n} pages"


def test_trim_size_is_driven_by_issue_yaml(issue_dir, tmp_path):
    """Changing the trim must be an issue.yaml edit only — no CSS, no
    Python. This is the test that keeps that promise honest."""
    geometry = "trim:\n  width_pt: 400\n  height_pt: 600\nbleed_pt: 12\n"
    pdf = build(issue_dir(geometry=geometry), tmp_path / "out")
    page = PdfReader(str(pdf)).pages[0]
    assert float(page.trimbox.width) == pytest.approx(400, abs=0.01)
    assert float(page.trimbox.height) == pytest.approx(600, abs=0.01)
    assert float(page.mediabox.width) == pytest.approx(424, abs=0.01)
    assert float(page.mediabox.height) == pytest.approx(624, abs=0.01)


def test_proof_is_marked_and_never_mistaken_for_the_upload(issue_dir,
                                                            tmp_path):
    """WeasyPrint draws crop marks inside the existing bleed rather than
    growing the page, so the two files are the same size. The name is what
    keeps them apart, and preflight skips anything named _proof."""
    d = issue_dir()
    plain = build(d, tmp_path / "out")
    proof = build(d, tmp_path / "out", proof=True)
    assert "_proof" in proof.name and "_proof" not in plain.name
    assert plain.read_bytes() != proof.read_bytes()

    plain_page = PdfReader(str(plain)).pages[0]
    proof_page = PdfReader(str(proof)).pages[0]
    assert float(plain_page.mediabox.width) == float(proof_page.mediabox.width)
    # the marks themselves are extra drawing operations on the page
    assert (len(proof_page.get_contents().get_data()) >
            len(plain_page.get_contents().get_data()))


def test_missing_wordmark_is_a_hard_error(issue_dir, tmp_path):
    """The SQ wordmark is supplied artwork, never set in type. A missing
    file must stop the build, not fall back to web type."""
    d = issue_dir()
    (d / "images/mark.png").unlink()
    with pytest.raises(ContentError, match="mark artwork not found"):
        build(d, tmp_path / "out")


def test_byline_card_carries_no_qr_code(issue_dir, tmp_path):
    """Summer 2026 put a QR of the source URL in every byline card.
    Discontinued from Fall 2026, and it must not come back: the url stays
    in frontmatter and prints in the contents listing, but nothing
    generates an image for it."""
    from sq.content import load_issue
    from sq.render import article_html

    issue = load_issue(issue_dir())
    html = article_html(issue, issue["articles"][0])
    card = html[html.index('<aside class="byline"'):html.index("</aside>")]
    assert "<img" not in card
    assert "qr" not in html.lower()
    assert "example.com" not in card       # the url is not rendered here


def test_long_table_repeats_its_header_across_pages(issue_dir, tmp_path):
    """A table longer than a page must break rather than being shoved
    whole onto the next one, and the header has to come with it."""
    rows = "\n".join(f"| {y} | NHL | Event number {y} |"
                      for y in range(1950, 2030))
    table = ("|+ A Long Table\n| Year | League | Event |\n"
             "|---|---|---|\n" + rows)
    d = issue_dir(body="Short.")
    art = d / "articles/01-a.md"
    art.write_text(art.read_text() + "\n\n" + table + "\n")

    pdf = build(d, tmp_path / "out")
    pages = [p.extract_text() for p in PdfReader(str(pdf)).pages]
    with_rows = [i for i, t in enumerate(pages) if "Event number" in t]
    assert len(with_rows) > 1, "80-row table did not break across pages"
    for i in with_rows:
        assert "League" in pages[i], f"header missing on page {i + 1}"


@pytest.mark.parametrize("filler", [0, 40, 80, 120, 160])
def test_a_table_never_strands_one_or_two_rows(issue_dir, tmp_path, filler):
    """Row orphans and widows. CSS orphans/widows only govern line boxes,
    so sq.css spells out the row equivalent with break-after/break-before
    on the first and last two rows. Whatever the table lands on, a split
    has to leave at least three rows on each side.

    The `filler` sweep walks the table's start down the page so the break
    falls at a different row each time — which is the only way to catch
    this, since any single offset looks fine.
    """
    rows = "\n".join(f"| {y} | NHL | Event number {y} |"
                      for y in range(1950, 1985))
    table = ("|+ A Long Table\n| Year | League | Event |\n"
             "|---|---|---|\n" + rows)
    d = issue_dir(body="Word " * filler)
    art = d / "articles/01-a.md"
    art.write_text(art.read_text() + "\n\n" + table + "\n")

    pdf = build(d, tmp_path / "out")
    per_page = [p.extract_text().count("Event number")
                for p in PdfReader(str(pdf)).pages]
    chunks = [n for n in per_page if n]
    assert sum(chunks) == 35, f"lost rows: {chunks}"
    assert min(chunks) >= 3, f"stranded rows with filler={filler}: {chunks}"


# --- drop caps -------------------------------------------------------------

@pytest.mark.parametrize("src,want", [
    ("In the early 1950s",
     '<span class="dropcap-letter">I</span>n the early 1950s'),
    # the cap must stay outside-in when the paragraph opens a small-caps run
    ("{sc}MARCUS HALLOWAY{/sc} in his warmups",
     '<span class="sc"><span class="dropcap-letter">M</span>'
     'ARCUS HALLOWAY</span> in his warmups'),
    # an opening quote rides along with the letter, as ::first-letter would
    ("“Quoted opening",
     '<span class="dropcap-letter">“Q</span>uoted opening'),
    ("**Bold** start",
     '<strong><span class="dropcap-letter">B</span>old</strong> start'),
    # an escaped entity must not be split down the middle
    ("A & B", '<span class="dropcap-letter">A</span> &amp; B'),
])
def test_dropcap_wraps_the_opening_character(src, want):
    from sq.render import dropcap, inline
    assert dropcap(inline(src)) == want


def test_dropcap_is_a_real_element_not_first_letter():
    """WeasyPrint reserves no advance width for a floated ::first-letter,
    so the first line of the paragraph runs underneath the cap and the
    second character vanishes behind it. Lines two and three clear it
    correctly, which is exactly what makes the bug easy to miss — so this
    guards the stylesheet against going back."""
    import re

    from sq.render import STYLESHEET
    # strip comments first — the explanation above mentions the selector
    css = re.sub(r"/\*.*?\*/", "", STYLESHEET.read_text(), flags=re.S)
    assert "::first-letter" not in css
    assert ".dropcap-letter" in css


def test_first_paragraph_gets_a_cap_and_later_ones_do_not(issue_dir):
    from sq.content import load_issue
    from sq.render import article_html

    issue = load_issue(issue_dir())
    html = article_html(issue, issue["articles"][0])
    assert html.count('class="dropcap-letter"') == 1


# --- wordmark drop shadow --------------------------------------------------

def test_cover_wordmark_gets_a_generated_drop_shadow(issue_dir):
    """WeasyPrint has no `filter: drop-shadow`, and `box-shadow` on an
    <img> shadows the element's rectangle rather than the silhouette —
    plainly wrong on a transparent wordmark. So it is composited from the
    alpha channel at build time, like the contents variant."""
    from PIL import Image

    from sq.content import SHADOW_PAD, load_issue
    d = issue_dir()
    issue = load_issue(d)
    gen = d / issue["mark"]["shadow_image"]
    assert gen.exists()

    src = Image.open(d / issue["mark"]["image"])
    out = Image.open(gen)
    # padded so the blur is not clipped at the canvas edge
    assert out.size[0] == src.size[0] + 2 * round(src.size[0] * SHADOW_PAD)
    # and the shadow actually put ink outside the original silhouette
    assert out.getchannel("A").getbbox() != (0, 0, *out.size)


def test_covers_use_the_shadowed_mark_and_contents_does_not(issue_dir):
    """A drop shadow belongs over photography, not on a white page."""
    from sq.content import load_issue
    from sq.render import contents_page, cover_page

    issue = load_issue(issue_dir())
    front = cover_page(issue, "cover", "front", "X", 100)
    toc = contents_page(issue)
    assert issue["mark"]["shadow_image"] in front
    assert issue["mark"]["shadow_image"] not in toc
    assert issue["mark"]["ink_image"] in toc


def test_shadow_widens_the_placement_to_keep_the_glyph_size(issue_dir):
    """The padding must not shrink the wordmark: the placed width grows by
    the same fraction, so the glyph still lands at the size asked for."""
    import re

    from sq.content import SHADOW_PAD, load_issue
    from sq.render import cover_page

    issue = load_issue(issue_dir())
    html = cover_page(issue, "cover", "front", "X", 100)
    placed = float(re.search(r"width:([\d.]+)pt", html).group(1))
    assert placed == pytest.approx(100 * (1 + 2 * SHADOW_PAD), abs=0.01)


# --- lede photo and the byline card -----------------------------------------

def test_byline_follows_a_full_width_lede_photo(issue_dir):
    """An article opening on a full-width photograph should not strand the
    byline card on a row of its own above it — the card belongs in the
    first paragraph of text, floated as usual."""
    from sq.content import load_issue
    from sq.render import article_html

    d = issue_dir()
    art = d / "articles/01-a.md"
    _, frontmatter, body = art.read_text().split("---", 2)
    art.write_text(f"---{frontmatter}---\n\n"
                   f"![A lede photograph](images/plate.jpg)\n{body}")

    issue = load_issue(d)
    html = article_html(issue, issue["articles"][0])
    assert html.index("<figure") < html.index('class="byline"')


def test_byline_comes_first_without_a_lede_photo(issue_dir):
    from sq.content import load_issue
    from sq.render import article_html

    issue = load_issue(issue_dir())
    html = article_html(issue, issue["articles"][0])
    assert html.index('class="byline"') < html.index("<figure")


# --- figures must never be split across a page ------------------------------

def test_split_figure_detection_and_nudge(issue_dir, tmp_path):
    """WeasyPrint lays floats out with page_is_empty=True, so
    `break-inside: avoid` cannot hold a figure together — it has nowhere
    to push it to. The build detects the split afterwards and moves the
    figure instead."""
    from sq.content import load_issue
    from sq.render import emit, _render, nudge, split_figures

    issue = load_issue(issue_dir())
    doc = _render(issue, emit(issue, 0), "none")
    assert split_figures(doc) == [], "sample fixture should lay out clean"

    art = issue["articles"][0]
    figs = [i for i, b in enumerate(art["blocks"]) if b["type"] == "figure"]
    before = list(art["blocks"])
    assert nudge(issue, f"fig-{art['slug']}-1") is True
    assert art["blocks"] != before, "nudge did not move anything"
    # a lede figure has nowhere to go
    assert nudge(issue, f"fig-{art['slug']}-0") is False


# --- cover stamp shadow ------------------------------------------------------

def test_stamp_carries_shadow_layers(issue_dir):
    """No text-shadow in WeasyPrint, so the stamp's shadow is offset
    copies drawn from data-text underneath the real words."""
    from sq.content import load_issue
    from sq.render import cover_page

    issue = load_issue(issue_dir())
    html = cover_page(issue, "cover", "front", "Fall 2026", 180)
    assert 'data-text="Fall 2026"' in html
    assert "<span>Fall 2026</span>" in html


# --- the fixed shape of an issue --------------------------------------------

def issue_shape(pdf):
    """(page count, blank page numbers, folio seen on each page)."""
    reader = PdfReader(str(pdf))
    blanks, folios = [], {}
    for i, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").strip()
        if not text:
            blanks.append(i)
        words = text.split()
        if words and words[-1].isdigit():
            folios[i] = int(words[-1])
    return len(reader.pages), blanks, folios


def test_every_issue_has_its_blank_leaves(issue_dir, tmp_path):
    """Front cover, blank inside it, contents, blank behind the contents —
    and at the end, a blank inside the back cover before the back cover."""
    pdf = build(issue_dir(), tmp_path / "out")
    n, blanks, _ = issue_shape(pdf)
    assert n % 4 == 0
    assert 2 in blanks, "no blank inside the front cover"
    assert 4 in blanks, "no blank behind the contents leaf"
    assert n - 1 in blanks, "no blank inside the back cover"
    assert n not in blanks, "the back cover must not be blank"


def test_numbering_starts_at_the_contents(issue_dir, tmp_path):
    """The contents is the third leaf but page 1 of the numbering, so the
    first article opens on PDF page 5 carrying folio 3. WeasyPrint only
    honours a page-counter reset on a named @page, not on the element."""
    pdf = build(issue_dir(), tmp_path / "out")
    _, _, folios = issue_shape(pdf)
    assert folios.get(5) == 3, f"first article should carry folio 3: {folios}"
    for pdf_page, folio in folios.items():
        if pdf_page >= 5:
            assert folio == pdf_page - 2, \
                f"pdf page {pdf_page} shows folio {folio}, expected {pdf_page - 2}"


def test_covers_and_contents_carry_no_folio(issue_dir, tmp_path):
    pdf = build(issue_dir(), tmp_path / "out")
    n, _, folios = issue_shape(pdf)
    for p in (2, 3, 4, n - 1):
        assert p not in folios, f"page {p} should have no folio"


# --- print vs screen ---------------------------------------------------------

def page_lefts(doc):
    """Content-box left edge of each page, in points."""
    return [round(p._page_box.content_box_x() * 0.75, 1) for p in doc.pages]


def test_print_build_mirrors_the_gutter(issue_dir):
    """Recto pages carry the wide inside margin on the left, verso pages
    on the right — the gutter the binding eats into."""
    from sq.content import load_issue
    from sq.render import emit, _render

    issue = load_issue(issue_dir())
    lefts = page_lefts(_render(issue, emit(issue, 0), "none"))
    inside = issue["geometry"]["margin_inside"]
    outside = issue["geometry"]["margin_outside"]
    # drop the covers, which are full bleed at margin 0
    body = [x for x in lefts[4:] if x]
    assert body, "no body pages"
    assert set(body) == {inside, outside}, f"gutter not mirrored: {set(body)}"


def test_screen_build_does_not_move_the_margins(issue_dir):
    """A PDF read on screen has no binding, so a margin that shifts every
    page reads as a fault rather than a gutter."""
    from sq.content import load_issue
    from sq.render import emit, _render

    issue = load_issue(issue_dir())
    lefts = page_lefts(_render(issue, emit(issue, 0), "none", screen=True))
    body = [x for x in lefts[4:] if x]        # covers are margin 0
    assert len(set(body)) == 1, f"margins still move: {set(body)}"


def test_screen_build_paginates_identically_to_print(issue_dir, tmp_path):
    """Symmetric margins are set at the mean of inside and outside, so the
    column keeps its printed width and nothing reflows."""
    from sq.content import load_issue
    from sq.render import emit, _render

    issue = load_issue(issue_dir())
    a = _render(issue, emit(issue, 0), "none")
    b = _render(issue, emit(issue, 0), "none", screen=True)
    assert len(a.pages) == len(b.pages)

    pdf_p = build(issue_dir(), tmp_path / "p")
    pdf_s = build(issue_dir(), tmp_path / "s", screen=True)
    assert "_screen" in pdf_s.name and "_screen" not in pdf_p.name
    assert (len(PdfReader(str(pdf_p)).pages)
            == len(PdfReader(str(pdf_s)).pages))


# --- the about page ----------------------------------------------------------

ABOUT_YAML = """about:
  heading: Stan Quarterly
  subheading: How we make this thing
  notes: A note about this particular issue.
"""


def with_about(issue_dir, extra=""):
    d = issue_dir()
    y = d / "issue.yaml"
    y.write_text(y.read_text() + "\n" + ABOUT_YAML + extra)
    return d


def test_no_about_block_means_no_about_page(issue_dir, tmp_path):
    """The page is opt-in — an issue without the block must not grow one."""
    pdf = build(issue_dir(), tmp_path / "out")
    text = "\n".join(p.extract_text() or "" for p in PdfReader(str(pdf)).pages)
    assert "How we make this thing" not in text


def test_about_page_is_the_last_printed_leaf(issue_dir, tmp_path):
    """A right-hand page, with a blank verso behind it, then the blank
    inside the back cover, then the back cover. That is page T-3, which is
    always one more than a multiple of four."""
    pdf = build(with_about(issue_dir), tmp_path / "out")
    reader = PdfReader(str(pdf))
    n = len(reader.pages)
    pages = [(p.extract_text() or "").strip() for p in reader.pages]
    at = next(i + 1 for i, t in enumerate(pages)
              if "How we make this thing" in t)

    assert at == n - 3, f"about on page {at}, expected {n - 3}"
    assert at % 2 == 1, "about page must be a recto"
    assert at % 4 == 1, "about page must be one more than a multiple of four"
    assert not pages[at], "no blank verso behind the about page"
    assert not pages[at + 1], "no blank inside the back cover"
    assert pages[at + 2], "the back cover must not be blank"
    assert n % 4 == 0


def test_about_page_carries_the_print_spec(issue_dir, tmp_path):
    pdf = build(with_about(issue_dir), tmp_path / "out")
    text = "\n".join(p.extract_text() or "" for p in PdfReader(str(pdf)).pages)
    assert "6.69" in text and "Mixam" in text


def test_qr_only_appears_when_a_url_is_given(issue_dir, tmp_path):
    """QR codes are gone from the byline cards for good. This one is the
    single exception, and it is opt-in."""
    from sq.content import load_issue

    plain = load_issue(with_about(issue_dir))
    assert "qr_image" not in (plain.get("about") or {})

    withurl = load_issue(with_about(
        issue_dir, "  pdf_url: https://example.com/x.pdf\n"))
    qr = withurl["about"]["qr_image"]
    assert (withurl["dir"] / qr).exists()


def test_no_qr_anywhere_but_the_about_page(issue_dir):
    """The rule that actually matters: articles and byline cards stay
    clear of them."""
    from sq.content import load_issue
    from sq.render import article_html

    issue = load_issue(with_about(
        issue_dir, "  pdf_url: https://example.com/x.pdf\n"))
    html = article_html(issue, issue["articles"][0])
    assert "qr" not in html.lower()
