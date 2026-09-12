"""Preflight an SQ issue against Mixam's requirements before upload.

Every check prints OK / WARN / FAIL. A FAIL means do not upload. The
failure modes this guards against are the quiet ones: an image that looks
fine on screen and prints soft, a font the engine substituted without
telling anyone, a page count that costs a reprint.
"""

import re
import unicodedata
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

from .content import fmt_date, load_issue

MIN_PPI, GOOD_PPI = 150, 300

# Mixam staples up to roughly this, depending on stock, then its calculator
# switches the order to perfect binding on its own. That needs a printed
# spine, and the build makes two separate full-bleed covers with no spine
# at all — so crossing this is a cover-artwork problem, not just a price
# change. See docs/MIXAM-RUNBOOK.md.
SADDLE_STITCH_LIMIT = 60

# Every placed width of the wordmark, in points. The cover figures come
# from render.mark_img(); the contents figure is `.contents-mark` in
# sq.css. The biggest placement is the one that decides whether the
# artwork is good enough, so all three are listed rather than just one.
MARK_WIDTHS = {"front cover": 100.0, "back cover": 74.0, "contents": 132.0}
MAX_COVER_CROP = 0.12
FLOAT_FRACTION = 0.44        # figure.right width, from sq.css


class Report:
    def __init__(self):
        self.fails = 0
        self.warns = 0

    def note(self, level, msg):
        if level == "FAIL":
            self.fails += 1
        elif level == "WARN":
            self.warns += 1
        print(f"  [{level}] {msg}")

    def ppi(self, r, msg):
        self.note("OK" if r >= GOOD_PPI else
                  ("WARN" if r >= MIN_PPI else "FAIL"), msg)

    def head(self, title):
        print(f"\n{title}")


def image_ppi(path: Path, placed_pt: float) -> float:
    with Image.open(path) as im:
        return im.size[0] / (placed_pt / 72.0)


def cover_ppi(path: Path, page_w: float, page_h: float):
    """Full-bleed art is scaled to COVER the page, so the tighter axis sets
    the scale and the other one gets cropped. Measuring against page width
    alone overstates the resolution and hides the crop entirely — a square
    image on this trim loses a third of its width."""
    with Image.open(path) as im:
        px_w, px_h = im.size
    scale = max(page_w / px_w, page_h / px_h)          # points per pixel
    shown_w, shown_h = px_w * scale, px_h * scale
    crop = max(0.0, (shown_w - page_w) / shown_w, (shown_h - page_h) / shown_h)
    return 72.0 / scale, crop


def cover_advice(path: Path, page_w: float, page_h: float) -> list:
    """Say what is actually wrong and what file would fix it.

    "92 ppi" on its own sends you looking for a bigger image, which is
    only half the story: a landscape photo on a portrait page throws most
    of itself away, so the number you have to beat is on the binding axis
    AFTER the crop, not the raw pixel count.
    """
    with Image.open(path) as im:
        px_w, px_h = im.size
    lines = []

    page_aspect, img_aspect = page_w / page_h, px_w / px_h
    need_w, need_h = round(page_w / 72 * GOOD_PPI), round(page_h / 72 * GOOD_PPI)
    binding = "height" if (page_h / px_h) > (page_w / px_w) else "width"
    have, need = ((px_h, need_h) if binding == "height" else (px_w, need_w))

    # Describe the shape by what actually happens to it, not by whether it
    # is landscape — a 0.80 portrait still loses width on a 0.66 page.
    shape = "landscape" if img_aspect > 1 else "portrait"
    if img_aspect > page_aspect * 1.02:
        lines.append(f"this is {shape} at {img_aspect:.2f} and the page is "
                     f"{page_aspect:.2f}, so it is relatively wide: the sides "
                     f"are cropped off and never printed")
    elif img_aspect < page_aspect * 0.98:
        lines.append(f"this is {shape} at {img_aspect:.2f} and the page is "
                     f"{page_aspect:.2f}, so it is relatively tall: the top "
                     f"and bottom are cropped off")

    if have < need:
        lines.append(f"{binding} is what sets the resolution here: {have} px "
                     f"where {need} is needed — {need / have:.2f}x short")
        lines.append(f"supply at least {need_w} x {need_h} px AFTER cropping "
                     f"to the page shape")
        if abs(img_aspect - page_aspect) > 0.02:
            lines.append(f"keeping this image's shape that means about "
                         f"{round(need_h * img_aspect)} x {need_h} px before "
                         f"the crop; a source already near {page_aspect:.2f} "
                         f"wastes nothing")
    return lines


def placed_width(block: dict, g: dict) -> float:
    if block["float"] == "full":
        return g["media_w"]
    if block["float"] in ("left", "right"):
        return g["column_w"] * FLOAT_FRACTION
    return g["column_w"]


# --- content checks --------------------------------------------------------

def check_images(issue: dict, rep: Report):
    rep.head("Images")
    g = issue["geometry"]

    art = issue["mark"]["image"]
    where, widest = max(MARK_WIDTHS.items(), key=lambda kv: kv[1])
    r = image_ppi(issue["dir"] / art, widest)
    rep.ppi(r, f"wordmark {Path(art).name}: {r:.0f} ppi at its largest "
               f"placement ({widest:g}pt, on the {where})")
    if r < GOOD_PPI:
        need = int(widest / 72 * GOOD_PPI)
        with Image.open(issue["dir"] / art) as im:
            have = im.size[0]
        print(f"         {have} px wide where {need} is wanted — "
              f"{need / have:.2f}x short")

    for key, label in (("cover", "front cover"), ("back_cover", "back cover")):
        p = issue["dir"] / issue[key]["image"]
        if not p.exists():
            rep.note("FAIL", f"{label} {issue[key]['image']}: MISSING")
            continue
        r, crop = cover_ppi(p, g["media_w"], g["media_h"])
        with Image.open(p) as im:
            px = "{} x {} px".format(*im.size)

        # Covers are always full bleed, so when no better art exists the
        # resolution is what gives. Setting cover.accept_low_resolution
        # records that decision once and downgrades the FAIL — a check
        # that can never pass is a check that stops being read.
        accepted = bool(issue[key].get("accept_low_resolution"))
        msg = f"{label} {p.name}: {r:.0f} ppi after cover-fill ({px})"
        if r < MIN_PPI and accepted:
            rep.note("WARN", msg + " — accepted in issue.yaml")
        else:
            rep.ppi(r, msg)
        if crop > MAX_COVER_CROP:
            rep.note("WARN", f"{label} loses {crop * 100:.0f}% of an axis "
                             f"to the crop")
        if (r < GOOD_PPI or crop > MAX_COVER_CROP) and not accepted:
            for line in cover_advice(p, g["media_w"], g["media_h"]):
                print(f"         {line}")

    for art in issue["articles"]:
        for b in art["blocks"]:
            if b["type"] != "figure":
                continue
            p = issue["dir"] / b["src"]
            if not p.exists():
                rep.note("FAIL", f"{art['slug']} {b['src']}: MISSING — "
                                 f"placeholder rendered in its place")
                continue
            w = placed_width(b, g)
            if b["float"] == "full":
                r, crop = cover_ppi(p, g["media_w"], g["media_h"])
                rep.ppi(r, f"{art['slug']} {p.name}: {r:.0f} ppi "
                           f"full-bleed page")
                if crop > MAX_COVER_CROP:
                    rep.note("WARN", f"{art['slug']} {p.name} loses "
                                     f"{crop * 100:.0f}% of an axis to the "
                                     f"full-bleed crop")
            else:
                r = image_ppi(p, w)
                rep.ppi(r, f"{art['slug']} {p.name}: {r:.0f} ppi at "
                           f"{w:.0f}pt wide")


# Two tiers, because the cost of being wrong differs. Anything in the
# pictographic planes will pull in a colour font and must not ship. The
# dingbats block is mostly ordinary monochrome glyphs — a tick or a star is
# legitimate type — so it only earns a look, not a blocked build.
# Spelled out as escapes so the ranges stay visible in a diff.
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF"      # emoji, pictographs, transport, symbols
    "\U0001FB00-\U0001FBFF"       # legacy computing symbols
    "\uFE0F"                       # VARIATION SELECTOR-16 (forces colour)
    "\u20E3]")                     # combining enclosing keycap

DINGBAT_RE = re.compile("[\u2600-\u27BF]")


def check_frontmatter(issue: dict, rep: Report):
    rep.head("Frontmatter")
    todos = 0
    for art in issue["articles"]:
        for field in ("title", "dek", "author", "publication", "date",
                      "url", "bio"):
            v = str(art.get(field, "") or "")
            if "# TODO" in v or "TODO" in v:
                todos += 1
                rep.note("FAIL", f"{art['slug']}: {field} still has a TODO")
        if not str(art.get("url", "")).startswith(("http://", "https://")):
            rep.note("FAIL", f"{art['slug']}: url is not a URL")

    # The about page is prose too, and the one line on it that cannot be
    # written in advance — `notes` names what is in the issue — is the
    # line most likely to still say TODO at upload. It used to be checked
    # nowhere, so it would have printed as written.
    for where, v in _strings(issue.get("about") or {}, "about"):
        if "TODO" in v:
            todos += 1
            rep.note("FAIL", f"{where} still has a TODO")

    if not todos:
        rep.note("OK", "no TODO placeholders in any article or on the "
                       "about page")


def _strings(node, path: str):
    """Every string in the about block, with a readable path to it, so a
    placeholder can be named rather than just counted. `sections` is a
    list of dicts, so this has to walk rather than scan one level."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def check_glyphs(issue: dict, rep: Report):
    """Colour fonts are unreliable in print — the Summer issue embedded
    Apple Color Emoji for a single character. Catch the character in the
    source, where it can actually be fixed."""
    rep.head("Glyphs")
    hits, maybes = set(), set()
    for art in issue["articles"]:
        texts = [str(art.get(f, "")) for f in ("title", "dek", "bio")]
        for b in art["blocks"]:
            texts += [str(b.get(k, "")) for k in
                      ("text", "caption", "attrib", "title")]
            texts += [str(c) for c in b.get("header", [])]
            texts += [str(c) for row in b.get("rows", []) for c in row]
        for t in texts:
            for ch in EMOJI_RE.findall(t):
                hits.add(f"{art['slug']}: U+{ord(ch):04X} "
                         f"{unicodedata.name(ch, 'unnamed')}")
            for ch in DINGBAT_RE.findall(t):
                maybes.add(f"{art['slug']}: {ch} U+{ord(ch):04X} "
                           f"{unicodedata.name(ch, 'unnamed')}")
    for h in sorted(hits):
        rep.note("FAIL", f"colour-emoji glyph in source — {h}")
    for h in sorted(maybes):
        rep.note("WARN", f"symbol that may resolve to a colour font — {h}")
    if not hits and not maybes:
        rep.note("OK", "no colour-emoji glyphs in the source text")


# --- font roles ------------------------------------------------------------
# Shared with `sq doctor`, which probes the same roles against a test
# render. Kept here because preflight is the gate: cli imports from
# preflight and not the other way round.

# Every role the stylesheet declares. --ui-face is unused at present but
# still probed: if furniture ever wants its own voice back, it should be
# a one-line change and not a discovery that the font went missing.
FONT_ROLES = [
    ("Headline", "--display-face", 900),
    ("Subhead", "--display-alt", 700),
    ("Body", "--body-face", 400),
    ("Furniture", "--cond-face", 400),
    ("Unused", "--ui-face", 400),
]


def font_matches(wanted: str, got: str) -> bool:
    """Did we get the family we asked for, or a fallback?

    Compares the family stem rather than the whole name. Pango describes
    a face by weight and width class, not by its full name, so
    `Mazzard H Black` legitimately comes back as
    `Mazzard-Heavy-Semi-Condensed` — the OTF has family "Mazzard",
    weight 900, width class 4. Insisting on an exact match reports a
    false failure on a font that is installed and correct.

    What actually needs catching is the family going missing on a fresh
    machine and the engine silently reaching for a fallback.
    """
    return _norm(wanted.split()[0]) in _norm(got)


def _norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def _first_family(var: str) -> str:
    """The first family named in a custom property in sq.css — the one
    that is actually wanted, before the fallbacks."""
    from .render import STYLESHEET
    css = STYLESHEET.read_text(encoding="utf-8")
    m = re.search(rf"{re.escape(var)}\s*:\s*([^;]+);", css)
    if not m:
        return "?"
    return m.group(1).split(",")[0].strip().strip('"').strip()


# --- PDF checks ------------------------------------------------------------

def embedded_fonts(reader: PdfReader) -> dict:
    seen = {}
    for page in reader.pages:
        fonts = (page.get("/Resources") or {}).get("/Font")
        if not fonts:
            continue
        for ref in fonts.values():
            obj = ref.get_object()
            base = str(obj.get("/BaseFont", "?")).lstrip("/")
            desc_fonts = obj.get("/DescendantFonts")
            desc = (desc_fonts[0].get_object().get("/FontDescriptor")
                    if desc_fonts else obj.get("/FontDescriptor"))
            embedded = False
            if desc:
                desc = desc.get_object()
                embedded = any(k in desc for k in
                               ("/FontFile", "/FontFile2", "/FontFile3"))
            seen[base] = seen.get(base, True) and embedded
    return seen


def check_pdf(pdf: Path, issue: dict, rep: Report):
    rep.head(f"PDF — {pdf.name}")
    g = issue["geometry"]
    reader = PdfReader(str(pdf))
    n = len(reader.pages)
    page = reader.pages[0]

    rep.note("OK" if n % 4 == 0 else "FAIL",
             f"{n} pages ({'multiple of 4' if n % 4 == 0 else 'NOT a multiple of 4'})")
    if n > SADDLE_STITCH_LIMIT:
        rep.note("WARN",
                 f"{n} pages is past the ~{SADDLE_STITCH_LIMIT}-page staple "
                 f"limit — Mixam will switch the order to perfect binding")
        print("         perfect binding needs a printed spine, and the build "
              "makes two separate")
        print("         covers with none. Check the binding on the calculator "
              "before confirming.")

    mw, mh = float(page.mediabox.width), float(page.mediabox.height)
    rep.note("OK" if abs(mw - g["media_w"]) < 1 and abs(mh - g["media_h"]) < 1
             else "FAIL",
             f"media box {mw:.2f} x {mh:.2f}pt "
             f"(want {g['media_w']:.2f} x {g['media_h']:.2f})")

    tw, th = float(page.trimbox.width), float(page.trimbox.height)
    declared = abs(tw - g["trim_w"]) < 1 and abs(th - g["trim_h"]) < 1
    rep.note("OK" if declared else "FAIL",
             f"trim box {tw:.2f} x {th:.2f}pt "
             f"({'declared' if declared else 'NOT declared — equals media box'})")

    bw, bh = float(page.bleedbox.width), float(page.bleedbox.height)
    rep.note("OK" if abs(bw - g["media_w"]) < 1 else "WARN",
             f"bleed box {bw:.2f} x {bh:.2f}pt")

    fonts = embedded_fonts(reader)
    missing = sorted(k for k, v in fonts.items() if not v)
    colour = sorted(k for k in fonts
                    if re.search(r"emoji|applecolor", k, re.I))
    for k in missing:
        rep.note("FAIL", f"font NOT embedded: {k}")
    for k in colour:
        rep.note("FAIL", f"colour font embedded: {k}")
    if not missing and not colour:
        rep.note("OK", f"all {len(fonts)} fonts embedded, none of them "
                       f"colour fonts")
    check_font_families(fonts, issue, rep)
    for k in sorted(fonts):
        print(f"         {k}")


def check_font_families(fonts: dict, issue: dict, rep: Report):
    """Is every embedded family one the stylesheet actually asked for?

    The other font checks answer "did it embed?" and "is it a colour
    font?" — both of which a silent substitution passes cleanly. Fall
    2026 went to print with its folios in Times New Roman because a
    comma-grouped margin-box rule was dropped and the engine fell back
    to the default serif; every existing check said OK. This is the one
    that would have caught it.

    Matching is by family stem, the same comparison `sq doctor` makes,
    so the weight-and-width names Pango emits do not read as strangers.
    """
    wanted = [_first_family(var) for _, var, _ in FONT_ROLES]
    accepted = [str(f) for f in (issue.get("fonts") or {}).get("accept", [])]

    strangers = [k for k in sorted(fonts)
                 if not any(font_matches(w, k) for w in wanted if w != "?")]
    if not strangers:
        rep.note("OK", f"every embedded family is a declared role")
        return

    for k in strangers:
        # Same escape hatch as the covers: a family that is genuinely
        # wanted is recorded once in issue.yaml rather than leaving a
        # standing FAIL that stops being read.
        if any(font_matches(a, k) for a in accepted):
            rep.note("WARN", f"font family not a declared role: {k} "
                             f"— accepted in issue.yaml")
        else:
            rep.note("FAIL", f"font family not a declared role: {k}")
            print("         nothing in sq.css asks for this — the engine "
                  "substituted it.")
            print("         Find what it is setting, or record it under "
                  "`fonts.accept` in issue.yaml.")


def mixam_numbers(pdf: Path, issue: dict):
    g = issue["geometry"]
    n = len(PdfReader(str(pdf)).pages)
    print(f"\nMixam order settings  ({pdf.name})")
    print(f"  PDF has ................. {n} pages")
    print(f"  Self-cover order ........ enter {n}")
    print(f"  'Add Cover (+4)' order .. enter {n - 4}")
    print(f"  'Add Cover', inners off . enter {n - 2}")
    print(f"  Trim .................... {g['trim_w'] / 72:.2f} x "
          f"{g['trim_h'] / 72:.2f} in  ({g['trim_w'] / 72 * 25.4:.0f} x "
          f"{g['trim_h'] / 72 * 25.4:.0f} mm)")
    print(f"  Bleed ................... {g['bleed'] / 72:.3f} in, already "
          f"in the file")
    print("  Upload .................. one multi-page PDF, covers included")
    print("  Whichever cover option you picked last time, pick it again —")
    print("  see docs/MIXAM-RUNBOOK.md before typing anything.")


def run(issue_dir: Path, pdf: Path | None = None) -> bool:
    issue = load_issue(issue_dir)
    rep = Report()
    print(f"Preflight — {issue['title']} {issue['issue']}")
    check_images(issue, rep)
    check_frontmatter(issue, rep)
    check_glyphs(issue, rep)
    if pdf and pdf.exists():
        check_pdf(pdf, issue, rep)
        mixam_numbers(pdf, issue)
    else:
        rep.head("PDF")
        rep.note("WARN", "no PDF given — run `sq build` first")

    print(f"\n{'PASS' if not rep.fails else 'ISSUES FOUND'} — "
          f"{rep.fails} FAIL, {rep.warns} WARN")
    return rep.fails == 0
