"""Markdown -> HTML + CSS Paged Media -> PDF, via WeasyPrint.

WeasyPrint was chosen over Typst because SQ's design floats byline cards and
images with prose wrapping around *and under* them, which Typst cannot do.
It also emits a correct TrimBox/BleedBox unprompted.

This module contains no visual decisions. Layout lives in template/sq.css;
the numbers live in template/geometry.css.in, filled from issue.yaml.
"""

import html
import re
from datetime import date
from pathlib import Path
from string import Template

from weasyprint import CSS, HTML

from .content import ContentError, fmt_date, load_issue

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "template"
STYLESHEET = TEMPLATE_DIR / "sq.css"
SCREEN_CSS = TEMPLATE_DIR / "screen.css"
GEOMETRY_IN = TEMPLATE_DIR / "geometry.css.in"

INLINE_STRONG = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.S)
INLINE_EM = re.compile(r"\*(?=\S)([^*]+?)(?<=\S)\*", re.S)

# The first visible character of a paragraph, skipping over any leading
# markup, and taking an opening quote or bracket along with the letter the
# way ::first-letter would.
DROPCAP_RE = re.compile(
    r"^((?:<[^>]+>|\s)*)"          # leading tags and whitespace
    r"([\u201C\u2018\u00AB(\[]?)"  # optional opening punctuation
    r"(&[#\w]+;|[^\s<])")          # an entity, or one character


def e(t) -> str:
    return html.escape(str(t))


def dropcap(html_text: str) -> str:
    """Wrap the opening character in a span for the drop cap.

    This is markup, not a visual decision — the size, face and float all
    stay in sq.css. It has to be a real element: WeasyPrint does not
    reserve advance width for a floated `::first-letter`, so the first
    line of the paragraph runs underneath the cap and the second character
    disappears behind it. Lines two and three clear it correctly, which is
    what makes the bug easy to miss.
    """
    m = DROPCAP_RE.match(html_text)
    if not m:
        return html_text
    lead, punct, char = m.groups()
    return (f'{lead}<span class="dropcap-letter">{punct}{char}</span>'
            f'{html_text[m.end():]}')


def inline(t) -> str:
    """Escape, then re-enable the small inline vocabulary: **strong**, *em*,
    and the {sc}...{/sc} small-caps marker that ingest.py leaves behind for
    sources that open sections with a capitalised run."""
    s = html.escape(str(t))
    s = INLINE_STRONG.sub(r"<strong>\1</strong>", s)
    s = INLINE_EM.sub(r"<em>\1</em>", s)
    return (s.replace("{sc}", '<span class="sc">')
             .replace("{/sc}", "</span>"))


# --- stylesheets -----------------------------------------------------------

def geometry_css(issue: dict, marks: str = "none",
                 mirror: bool = True) -> str:
    g = dict(issue["geometry"])
    g["marks"] = marks
    if not mirror:
        # Symmetric margins at the mean of the two, so the column keeps
        # exactly its printed width and the pagination does not move.
        side = (g["margin_inside"] + g["margin_outside"]) / 2
        g["margin_inside"] = g["margin_outside"] = side
    return Template(GEOMETRY_IN.read_text(encoding="utf-8")).substitute(
        {k: (f"{v:g}" if isinstance(v, float) else v) for k, v in g.items()})


# --- HTML emit -------------------------------------------------------------

def mark_img(issue: dict, width_pt: float, back: bool = False) -> str:
    """The wordmark is always supplied artwork. There is no type fallback —
    setting SQ in a substitute grotesque does not match the Mazzard
    original, so a missing file is an error, never something to paper over.
    load_issue() has already checked it exists."""
    from .content import SHADOW_PAD
    art = issue["mark"]["shadow_image_back" if back else "shadow_image"]
    # the shadow variant carries transparent padding so the blur is not
    # clipped; widening by the same fraction keeps the glyph itself at
    # exactly width_pt
    placed = width_pt * (1 + 2 * SHADOW_PAD)
    return (f'<div class="mark"><img class="markart" '
            f'style="width:{placed:g}pt" src="{e(art)}"></div>')


def cover_page(issue: dict, key: str, cls: str, stamp: str,
               mark_w: float) -> str:
    spec = issue[key]
    focus = spec.get("focus", "center")
    stamp = spec.get("stamp", stamp)
    return (f'<div class="bleed-page {cls}">'
            f'<img class="art" style="object-position:{e(focus)}" '
            f'src="{e(spec["image"])}">'
            f'{mark_img(issue, mark_w, back=(cls == "back"))}'
            # WeasyPrint has no text-shadow, so the stamp's shadow is two
            # offset copies drawn from data-text beneath the real words —
            # the nearest thing to the blur baked into the wordmark.
            f'<div class="stamp" data-text="{e(stamp)}">'
            f'<i>{e(stamp)}</i><span>{e(stamp)}</span></div>'
            f'</div>')


def contents_page(issue: dict) -> str:
    # Arranged the way Summer 2026 was laid out by hand: the wordmark large
    # and grey at the top left, the issue name and "Contents" ranged right
    # against it, and the colophon centred at the foot.
    h = ['<div class="contents">',
         '<div class="contents-head">',
         f'<img class="contents-mark" src="{e(issue["mark"]["ink_image"])}">',
         '<div class="contents-title">',
         f'<h1>{e(issue["issue"])}</h1><h2>Contents</h2>',
         '</div></div>']
    for art in issue["articles"]:
        h.append('<div class="toc-entry">'
                 f'<a class="t" href="#{art["slug"]}">{e(art["title"])}</a>'
                 f'<div class="meta">{e(art["author"])} &ndash; '
                 f'<i>{e(art["publication"])}</i> &ndash; '
                 f'{e(fmt_date(art["date"]))}'
                 f'<a href="#{art["slug"]}"></a></div>'
                 f'<div class="url">{e(art["url"])}</div></div>')
    h.append('<div class="contents-foot">')
    # inline() so the colophon can emphasise a phrase, as Summer's did
    h.append(f'<div class="colophon">{inline(issue.get("colophon", ""))}</div>')
    h.append("</div></div>")
    return "\n".join(h)


DEFAULT_ABOUT = [
    ("Made from Markdown", 
     "Each article is copied out of the browser and cleaned into a small "
     "Markdown dialect — a plain text file per piece, plus one settings "
     "file naming the covers, the trim size and the running order. "
     "Nothing about the layout is touched by hand."),
    ("Set by a stylesheet",
     "A build script turns those files into HTML and hands them to "
     "WeasyPrint, which does the typesetting from a single stylesheet. "
     "Drop caps, floated pictures with text wrapping under them, the "
     "contents page numbers, the folios — all of it falls out of that one "
     "file, so every issue sets the same way without anyone remembering "
     "how."),
    ("Where the code lives",
     "The builder is open, at __BUILDER__. It is the scripts, the "
     "stylesheet and a worked sample issue — everything needed to make a "
     "magazine, and nothing of this one. The words and photographs live "
     "in a second repository that stays private, because they are "
     "reprinted here and are not ours to hand out."),
    ("Checked before it prints",
     "A preflight step refuses the issue if a photograph would print soft, "
     "if a caption has drifted from its picture, if the page count is not "
     "a multiple of four, or if a font failed to embed. It prints the "
     "number to type into the printer's order form, which is not the same "
     "as the number of pages in the file."),
]


def about_page(issue: dict) -> str:
    """The colophon: how the issue is made, and how to read it on a screen.

    Laid out as the counterpart to the contents — wordmark left, headings
    ranged right against it.
    """
    cfg = issue.get("about") or {}
    g = issue["geometry"]
    h = ['<div class="about" id="about-page">',
         '<div class="contents-head">',
         f'<img class="contents-mark" src="{e(issue["mark"]["ink_image"])}">',
         '<div class="contents-title">',
         f'<h1>{e(cfg.get("heading", issue.get("title", "")))}</h1>',
         f'<h2>{e(cfg.get("subheading", "How we made this thing"))}</h2>',
         '</div></div>']

    sections = cfg.get("sections") or DEFAULT_ABOUT
    builder = cfg.get("builder_url", "")
    sections = [(t, x.replace("__BUILDER__", builder) if builder else
                 x.replace(" The builder is open, at __BUILDER__.", ""))
                for t, x in sections]
    if isinstance(sections, dict):
        sections = list(sections.items())
    h.append('<div class="about-body">')
    for title, text in sections:
        h.append(f'<div class="note"><h3>{inline(title)}</h3>'
                 f'<p>{inline(text)}</p></div>')

    if cfg.get("notes"):
        h.append(f'<div class="note issue-note">'
                 f'<h3>{e(cfg.get("notes_heading", "About this issue"))}</h3>'
                 f'<p>{inline(cfg["notes"])}</p></div>')
    h.append("</div>")

    if cfg.get("qr_image"):
        h.append('<div class="about-qr">')
        h.append(f'<img src="{e(cfg["qr_image"])}">')
        h.append(f'<div class="qr-how">{inline(cfg.get("qr_instructions", ""))}</div>')
        h.append("</div>")

    h.append('<div class="about-spec">'
             f'{g["trim_w"] / 72:.2f} &times; {g["trim_h"] / 72:.2f} in '
             f'({g["trim_w"] / 72 * 25.4:.0f} &times; '
             f'{g["trim_h"] / 72 * 25.4:.0f} mm) &middot; '
             f'{g["bleed"] / 72:.3f} in bleed &middot; saddle-stitched '
             f'&middot; printed by Mixam</div>')
    h.append("</div>")
    return "\n".join(h)


def figure_html(issue: dict, b: dict, fig_id: str = "") -> str:
    cls = b["float"]
    credit = (f'<span class="credit">{inline(b["credit"])}</span>'
              if b.get("credit") else "")
    cap = (f'<figcaption>{inline(b["caption"])}{credit}</figcaption>'
           if b["caption"] or credit else "")
    if (issue["dir"] / b["src"]).exists():
        body = f'<img src="{e(b["src"])}">'
    else:
        # Keep the layout honest while the real file is still being sourced;
        # preflight FAILs on every one of these.
        cls = (cls + " missing").strip()
        body = f'<div class="box" data-file="{e(b["src"])}"></div>'
    ident = f' id="{fig_id}"' if fig_id else ""
    return f'<figure class="{cls}"{ident}>{body}{cap}</figure>'


ALIGN_CLASS = {"left": "a-l", "center": "a-c", "right": "a-r"}


def table_html(b: dict) -> str:
    """A real table, in the issue's own type. Summer 2026 pasted its two
    tables in as screenshots, which is why they printed soft and in the
    wrong fonts.

    The header is a <thead> so WeasyPrint repeats it when a long table
    breaks across a page."""
    out = ['<table class="sqtable">']
    if b["title"]:
        out.append(f'<caption>{inline(b["title"])}</caption>')

    cells = "".join(
        f'<th class="{ALIGN_CLASS[a]}">{inline(c)}</th>'
        for c, a in zip(b["header"], b["align"]))
    out.append(f"<thead><tr>{cells}</tr></thead><tbody>")

    for row in b["rows"]:
        cells = "".join(
            f'<td class="{ALIGN_CLASS[a]}">{inline(c)}</td>'
            for c, a in zip(row, b["align"]))
        out.append(f"<tr>{cells}</tr>")

    out.append("</tbody></table>")
    return "".join(out)


def article_html(issue: dict, art: dict) -> str:
    blocks = art["blocks"]

    # An article that opens on a full-width photograph should not strand
    # the byline card on a row of its own above it. Emit the lede first,
    # then the card, so it floats into the opening paragraph as usual.
    lede = None
    if blocks and blocks[0]["type"] == "figure" and blocks[0]["float"] == "":
        lede, blocks = blocks[0], blocks[1:]

    out = [f'<section class="article" id="{art["slug"]}">',
           f'<h1>{inline(art["title"])}</h1>']
    if art.get("dek"):
        out.append(f'<p class="dek">{inline(art["dek"])}</p>')
    if lede:
        out.append(figure_html(issue, lede, f'fig-{art["slug"]}-0'))
    out.append('<aside class="byline">'
               f'<div class="who">{e(art["author"])}</div>'
               f'<div class="pub">{e(art["publication"])}</div>'
               f'<div class="when">{e(fmt_date(art["date"]))}</div>'
               '</aside>')

    first_para, n = True, 0
    for b in blocks:
        if b["type"] == "para":
            is_cap = b["dropcap"] or first_para
            first_para = False
            body = inline(b["text"])
            if is_cap:
                body = dropcap(body)
            out.append(f'<p class="{"dropcap" if is_cap else ""}">{body}</p>')
        elif b["type"] == "subhead":
            out.append(f'<h2 class="subhead">{inline(b["text"])}</h2>')
        elif b["type"] == "ornament":
            out.append('<div class="ornament">***</div>')
        elif b["type"] == "pullquote":
            attrib = (f'<div class="attrib">&mdash; {inline(b["attrib"])}</div>'
                      if b["attrib"] else "")
            out.append(f'<blockquote class="pull"><p>{inline(b["text"])}</p>'
                       f'{attrib}</blockquote>')
        elif b["type"] == "table":
            out.append(table_html(b))
        elif b["type"] == "figure":
            n += 1
            out.append(figure_html(issue, b, f'fig-{art["slug"]}-{n}'))

    out.append(f'<div class="bio"><div class="name">{e(art["author"])}</div>'
               f'<div class="text">{inline(art["bio"])}</div></div>')
    out.append("</section>")
    return "\n".join(out)


def emit(issue: dict, filler_pages: int = 0) -> str:
    h = ['<!DOCTYPE html><html><head><meta charset="utf-8">',
         f'<title>{e(issue["title"])} {e(issue["issue"])}</title>',
         "</head><body>"]
    # The fixed shape of every issue:
    #   1  front cover
    #   2  blank, inside the front cover
    #   3  contents        <- page 1 of the numbering
    #   4  blank, the back of the contents leaf
    #   5  first article   <- page 3 of the numbering
    #   ...
    #   n-1 blank, inside the back cover
    #   n  back cover
    h.append(cover_page(issue, "cover", "front", issue["issue"], 180))
    h.append('<div class="blank">&nbsp;</div>')
    h.append(contents_page(issue))
    h.append('<div class="blank">&nbsp;</div>')
    for art in issue["articles"]:
        h.append(article_html(issue, art))
    # Padding to a multiple of 4 sits before the inside-back blank, so the
    # last two leaves are always the blank and the back cover.
    for _ in range(filler_pages):
        h.append('<div class="filler">&nbsp;</div>')
    if issue.get("about"):
        # The about page is the last printed leaf: a recto, with the blank
        # verso behind it, then the blank inside the back cover, then the
        # back cover itself.
        h.append(about_page(issue))
        h.append('<div class="blank">&nbsp;</div>')
    h.append('<div class="blank">&nbsp;</div>')
    h.append(cover_page(issue, "back_cover", "back",
                        issue.get("subtitle", ""), 120))
    h.append("</body></html>")
    return "\n".join(h)


# --- render ----------------------------------------------------------------

def _render(issue: dict, source: str, marks: str, screen: bool = False):
    gen = issue["dir"] / "generated"
    gen.mkdir(parents=True, exist_ok=True)
    geo = gen / ("geometry-screen.css" if screen else "geometry.css")
    geo.write_text(geometry_css(issue, marks, mirror=not screen),
                   encoding="utf-8")
    page = gen / "index.html"
    page.write_text(source, encoding="utf-8")
    sheets = [CSS(filename=str(geo)), CSS(filename=str(STYLESHEET))]
    if screen:
        sheets.append(CSS(filename=str(SCREEN_CSS)))
    doc = HTML(filename=str(page), base_url=str(issue["dir"]) + "/").render(
        stylesheets=sheets)
    return doc


def _walk(box):
    yield box
    for kid in getattr(box, "children", []) or []:
        yield from _walk(kid)


def page_of(doc, element_id: str):
    """Which page a given element landed on, 1-based, or None."""
    for n, page in enumerate(doc.pages, 1):
        for box in _walk(page._page_box):
            el = getattr(box, "element", None)
            if el is not None and el.get("id") == element_id:
                return n
    return None


def split_figures(doc) -> list:
    """Figures whose image and caption landed on different pages.

    A floated figure can be split by WeasyPrint whatever the stylesheet
    says: float_layout() lays floats out with page_is_empty=True, so
    `break-inside: avoid` has nowhere to push them to and is ignored.
    The only reliable remedy is to notice afterwards and move the figure.
    """
    # Only the <figure> carries the id — its img and figcaption children do
    # not — so the test is simply whether the figure's own box turns up on
    # more than one page. A split float does exactly that.
    seen = {}
    for n, page in enumerate(doc.pages):
        for box in _walk(page._page_box):
            if getattr(box, "element_tag", None) != "figure":
                continue
            el = getattr(box, "element", None)
            fid = el.get("id") if el is not None else None
            if fid and fid.startswith("fig-"):
                seen.setdefault(fid, set()).add(n)
    return sorted(f for f, pages in seen.items() if len(pages) > 1)


def nudge(issue: dict, fid: str) -> bool:
    """Move a split figure one block later, so the float starts on the
    next page instead of straddling the break. What a layout editor would
    do by hand. Returns False when there is nowhere left to move it."""
    slug, _, idx = fid.rpartition("-")
    slug = slug[len("fig-"):]
    art = next((a for a in issue["articles"] if a["slug"] == slug), None)
    if art is None or idx == "0":       # the lede stays put
        return False
    figs = [i for i, b in enumerate(art["blocks"]) if b["type"] == "figure"]
    pos = figs[int(idx) - 1]
    if pos + 1 >= len(art["blocks"]):
        return False
    b = art["blocks"].pop(pos)
    art["blocks"].insert(pos + 1, b)
    return True


def build(issue_dir: Path, out_dir: Path, proof: bool = False,
          stamp: str | None = None, screen: bool = False) -> Path:
    """Render the issue, pad to a multiple of 4, write the PDF, return its
    path. Two passes: the filler count isn't known until the first render
    has told us how long the issue is."""
    issue = load_issue(issue_dir)
    marks = "crop cross" if proof else "none"

    doc = _render(issue, emit(issue, 0), marks, screen)

    # A photograph and its caption are one thing and must never be split
    # across a page. Detect it and move the figure, then re-render, until
    # the issue is clean or nothing more can be moved.
    for _ in range(8):
        bad = split_figures(doc)
        if not bad:
            break
        if not any(nudge(issue, f) for f in bad):
            print(f"  warning: could not unsplit {', '.join(bad)}")
            break
        doc = _render(issue, emit(issue, 0), marks, screen)

    if issue.get("about"):
        # The about page has to be the recto of the penultimate leaf, so
        # that a blank verso, the blank inside the back cover and the back
        # cover follow it. That page is always one more than a multiple of
        # four; pad forward until it lands there.
        at = page_of(doc, "about-page")
        pad = 0
        if at is not None:
            while (at + pad) % 4 != 1:
                pad += 1
        if pad:
            doc = _render(issue, emit(issue, pad), marks, screen)
    else:
        pad = (4 - len(doc.pages) % 4) % 4
        if pad:
            doc = _render(issue, emit(issue, pad), marks, screen)
    if len(doc.pages) % 4:
        raise ContentError(
            f"padding failed: {len(doc.pages)} pages is not a multiple of 4")

    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9]+", "_", issue["issue"]).strip("_")
    name = (f"{issue.get('abbr', 'SQ')}_{slug}_"
            f"{stamp or date.today().isoformat()}"
            f"{'_proof' if proof else ''}{'_screen' if screen else ''}.pdf")
    pdf = out_dir / name
    doc.write_pdf(str(pdf))
    return pdf
