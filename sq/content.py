"""Content layer for Stan Quarterly.

Parses the SQ Markdown dialect into a neutral block list, so the renderer
consumes structure rather than syntax and the layout backend stays
swappable.

SQ Markdown dialect
-------------------
  ---                YAML frontmatter
  ## Heading         section subhead
  @@ text...         paragraph rendered with a drop cap
  ![cap](src)        figure with caption, full column width
  ![cap | credit](src)  caption plus a photo credit, set separately
  ![cap](src){.right} figure floated right, text wraps around and under
  ![cap](src){.left}  the same, floated left — alternate them down a long piece
  ![cap](src){.full} full-bleed image page
  > quote            pull quote; a final `-- Name` line is the attribution
  ***                section-break ornament
  | a | b |          table: GFM pipe syntax, with `|+ Title` for a title
                     row and :---: / ---: in the separator for alignment
  <!-- note -->      dropped; `sq add` leaves these for the editor
  text               ordinary paragraph

Inline: *em* and **strong** only. Straight quotes and --/--- are converted
to typographic equivalents here, at parse time, so the renderer never has
to think about punctuation.
"""

import re
from pathlib import Path

import yaml

FIG_RE = re.compile(
    r"^!\[(?P<cap>.*)\]\((?P<src>[^)]+)\)(?:\{\.(?P<cls>[a-z-]+)\})?\s*$")
COMMENT_RE = re.compile(r"^<!--.*?-->$", re.S)
ORNAMENT_RE = re.compile(r"^\*{3,}$")
TABLE_TITLE_RE = re.compile(r"^\|\+\s*(?P<title>.*?)\s*\|?\s*$")
# a separator row is all dashes and colons: |---|:---:|---:|
TABLE_SEP_RE = re.compile(r"^\|[\s|:-]+\|?\s*$")
CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
# ` | ` inside a figure's alt text separates the caption from the photo
# credit. The credit is metadata about the image, not the tail of the
# caption's sentence, and it is set differently.
CREDIT_SPLIT_RE = re.compile(r"(?<!\\) \| ")

FIGURE_CLASSES = {"", "left", "right", "full"}

# dek is optional; everything else must be present, or the build stops.
TODO = "# TODO"
REQUIRED_FIELDS = ("title", "author", "publication", "date", "url", "bio")

DEFAULT_GEOMETRY = {
    "trim": {"width_pt": 481.68, "height_pt": 737.28},
    "bleed_pt": 9.0,
    "quiet_pt": 18.0,
    "margins_pt": {"top": 46.0, "bottom": 42.0, "inside": 54.0, "outside": 44.0},
}


class ContentError(Exception):
    """A problem in the source the user has to fix. Reported without a
    traceback — these are editing mistakes, not crashes."""


# --- typography ------------------------------------------------------------

def typographic(s: str) -> str:
    """Straight quotes and ASCII dashes to their real typographic forms.

    `---` is an em dash and `--` an en dash, the usual Markdown convention.
    Source-specific quirks (ESPN pastes use ` -- ` for an em dash) are
    handled in ingest.py, which writes real dashes into the Markdown, so
    they never reach this function.
    """
    s = s.replace("---", "—").replace("--", "–")

    # Double quotes: opening after start, whitespace, or an opening bracket
    # or dash; closing everywhere else.
    s = re.sub(r'(^|[\s([{–—])"', r"\1“", s)
    s = s.replace('"', "”")

    # Single quotes. Leading elision first ('90s, 'til) so it isn't mistaken
    # for an opening quote, then opening, then everything else as apostrophe
    # or closing quote — which share a glyph.
    s = re.sub(r"(^|[\s([{–—])'(?=\d{2}s\b|(?:til|tis|em|cause)\b)",
               r"\1’", s, flags=re.I)
    s = re.sub(r"(^|[\s([{–—])'", r"\1‘", s)
    s = s.replace("'", "’")

    # Ellipsis last, so it can't interfere with the quote rules above.
    s = re.sub(r"\.\s?\.\s?\.", "…", s)
    return s


def split_credit(raw: str):
    """`Caption text | Photo: Someone` -> ("Caption text", "Photo: Someone").

    Splits on the LAST ` | `, so a caption may contain one. A literal
    pipe is escaped as \\|.
    """
    parts = CREDIT_SPLIT_RE.split(raw)
    unescape = lambda t: t.replace("\\|", "|").strip()
    if len(parts) < 2:
        return unescape(raw), ""
    return unescape(" | ".join(parts[:-1])), unescape(parts[-1])


# --- article parsing -------------------------------------------------------

def parse_article(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    if not raw.lstrip().startswith("---"):
        raise ContentError(f"{path}: missing YAML frontmatter")
    try:
        _, fm, body = raw.split("---", 2)
    except ValueError:
        raise ContentError(f"{path}: frontmatter is not closed with ---")

    try:
        meta = yaml.safe_load(fm) or {}
    except yaml.YAMLError as exc:
        raise ContentError(f"{path}: frontmatter is not valid YAML — {exc}")
    if not isinstance(meta, dict):
        raise ContentError(f"{path}: frontmatter must be a YAML mapping")

    # A key that is absent entirely is an editing mistake and stops the
    # build. A key that is present but empty is the placeholder `sq add`
    # leaves behind — note that `bio: # TODO` is a YAML *comment*, so the
    # value parses as null. That must still build, so the layout can be
    # seen, and preflight is what refuses to let it reach Mixam.
    absent = [f for f in REQUIRED_FIELDS if f not in meta]
    if absent:
        raise ContentError(
            f"{path.name}: frontmatter has no {', '.join(absent)} field. "
            f"Every article needs {', '.join(REQUIRED_FIELDS)} "
            f"(dek is optional).")
    for field in REQUIRED_FIELDS:
        if not str(meta[field] or "").strip():
            meta[field] = TODO

    # Frontmatter gets the same typographic pass the body does. Without
    # it a straight apostrophe typed into a title prints as one, in the
    # headline and again on the contents page, while the prose around it
    # is correctly curled.
    for field in ("title", "dek", "author", "publication", "bio"):
        if isinstance(meta.get(field), str):
            meta[field] = typographic(meta[field])

    meta.setdefault("dek", "")
    meta["slug"] = path.stem
    meta["source_path"] = path
    meta["blocks"] = parse_blocks(body)
    return meta


def parse_blocks(body: str) -> list:
    blocks = []
    for chunk in re.split(r"\n\s*\n", body.strip()):
        chunk = chunk.strip()
        if not chunk or COMMENT_RE.match(chunk):
            continue

        if ORNAMENT_RE.match(chunk):
            blocks.append({"type": "ornament"})
            continue

        m = FIG_RE.match(chunk)
        if m:
            cls = m.group("cls") or ""
            if cls not in FIGURE_CLASSES:
                raise ContentError(
                    f"unknown figure class {{.{cls}}} on {m.group('src')} — "
                    f"expected one of .left, .right, .full, or none")
            caption, credit = split_credit(m.group("cap") or "")
            blocks.append({
                "type": "figure",
                "src": m.group("src"),
                "caption": typographic(caption),
                "credit": typographic(credit),
                "float": cls,
            })
            continue

        if chunk.startswith("|"):
            blocks.append(_parse_table(chunk))
            continue

        if chunk.startswith("## "):
            blocks.append({"type": "subhead",
                           "text": typographic(chunk[3:].strip())})
            continue

        if chunk.startswith(">"):
            lines = [ln.lstrip("> ").rstrip() for ln in chunk.splitlines()]
            attrib = ""
            if lines and lines[-1].startswith(("-- ", "— ")):
                attrib = lines.pop().lstrip("-— ").strip()
            blocks.append({
                "type": "pullquote",
                "text": typographic(" ".join(l for l in lines if l)),
                "attrib": typographic(attrib),
            })
            continue

        dropcap = chunk.startswith("@@ ")
        if dropcap:
            chunk = chunk[3:]
        blocks.append({
            "type": "para",
            "text": typographic(" ".join(chunk.split())),
            "dropcap": dropcap,
        })
    return blocks


def _split_row(line: str) -> list:
    """Split a pipe row into cells. A literal pipe inside a cell is escaped
    as \\|."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip().replace("\\|", "|") for c in CELL_SPLIT_RE.split(line)]


def _alignments(sep_row: str) -> list:
    out = []
    for cell in _split_row(sep_row):
        left, right = cell.startswith(":"), cell.endswith(":")
        out.append("center" if left and right else
                   "right" if right else "left")
    return out


def _parse_table(chunk: str) -> dict:
    """GFM pipe tables. A header row and a separator row are both required —
    a block of pipe lines without a separator is a mistake worth reporting,
    not something to render as a paragraph full of pipes."""
    lines = [l.strip() for l in chunk.splitlines() if l.strip()]

    title = ""
    if TABLE_TITLE_RE.match(lines[0]) and lines[0].startswith("|+"):
        title = typographic(TABLE_TITLE_RE.match(lines[0]).group("title"))
        lines = lines[1:]

    sep = next((i for i, l in enumerate(lines) if TABLE_SEP_RE.match(l)), None)
    if sep is None:
        raise ContentError(
            "table has no separator row. A table needs a header, then a "
            "row like |---|---|, then the body:\n"
            "    | Year | Event |\n"
            "    |---|---|\n"
            "    | 1994 | Rangers win the Stanley Cup |")
    if sep != 1:
        raise ContentError(
            f"table separator is on line {sep + 1}; it must come directly "
            f"after the single header row")

    header = [typographic(c) for c in _split_row(lines[0])]
    align = _alignments(lines[sep])
    if len(align) != len(header):
        raise ContentError(
            f"table separator has {len(align)} columns but the header has "
            f"{len(header)}")

    rows = []
    for n, line in enumerate(lines[sep + 1:], start=sep + 2):
        cells = [typographic(c) for c in _split_row(line)]
        if len(cells) != len(header):
            raise ContentError(
                f"table row {n} has {len(cells)} cells but the header has "
                f"{len(header)}: {line!r}")
        rows.append(cells)
    if not rows:
        raise ContentError("table has a header but no body rows")

    return {"type": "table", "title": title, "header": header,
            "align": align, "rows": rows}


# --- issue loading ---------------------------------------------------------

def derive_mark_variant(issue_dir: Path, src_rel: str, rgb=(17, 17, 17)) -> str:
    """The wordmark is a single-colour silhouette, so the dark version used
    on the contents page is recoloured from the supplied artwork's alpha
    rather than being a second file the user has to keep in sync."""
    from PIL import Image
    out_rel = "generated/sq-mark-ink.png"
    out = issue_dir / out_rel
    out.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(issue_dir / src_rel) as im:
        alpha = im.convert("RGBA").getchannel("A")
        flat = Image.new("RGBA", alpha.size, (*rgb, 0))
        flat.putalpha(alpha)
        flat.save(out)
    return out_rel


# Drop shadow for the covers, all as a fraction of the artwork's width so
# it looks the same whatever resolution the wordmark is supplied at.
SHADOW_OFFSET = 0.013
SHADOW_BLUR = 0.015
SHADOW_ALPHA = 220
# The artwork is drawn flush to its canvas, so the shadow needs room. The
# padding is given back to the renderer, which widens the placement by the
# same fraction — the glyph lands at exactly the size it always did.
SHADOW_PAD = 0.06


def derive_mark_shadow(issue_dir: Path, src_rel: str,
                       mark_alpha: float = 1.0, suffix: str = "") -> str:
    """The wordmark with a small drop shadow baked in, for the covers.

    WeasyPrint has no `filter: drop-shadow`, and `box-shadow` on an <img>
    shadows the element's rectangle rather than the silhouette — which on
    a transparent wordmark is plainly wrong. So it is composited here,
    from the alpha channel, the same way the contents variant is.
    """
    from PIL import Image, ImageFilter
    out_rel = f"generated/sq-mark-shadow{suffix}.png"
    out = issue_dir / out_rel
    out.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(issue_dir / src_rel) as im:
        art = im.convert("RGBA")
    w, h = art.size
    pad = round(w * SHADOW_PAD)
    canvas = (w + 2 * pad, h + 2 * pad)

    shadow = Image.new("RGBA", canvas, (0, 0, 0, 0))
    tint = Image.new("RGBA", canvas, (0, 0, 0, SHADOW_ALPHA))
    mask = Image.new("L", canvas, 0)
    off = round(w * SHADOW_OFFSET)
    mask.paste(art.getchannel("A"), (pad + off, pad + off))
    mask = mask.filter(ImageFilter.GaussianBlur(w * SHADOW_BLUR))
    shadow.paste(tint, (0, 0), mask)

    if mark_alpha < 1.0:
        # Fade the MARK but not its shadow. Doing this with CSS opacity
        # fades both, which is what made the back cover's shadow vanish.
        a = art.getchannel("A").point(lambda v: round(v * mark_alpha))
        art.putalpha(a)
    shadow.alpha_composite(art, (pad, pad))
    shadow.save(out)
    return out_rel


def derive_qr(issue_dir: Path, url: str) -> str:
    """QR for the online copy, used on the about page and nowhere else.

    QR codes were dropped from the byline cards after Summer 2026 and must
    not come back there. This one is a deliberate exception: it is how Stan
    gets at the PDF on an iPad, so it belongs with the instructions for
    doing that.
    """
    import segno
    out_rel = "generated/about-qr.png"
    out = issue_dir / out_rel
    out.parent.mkdir(parents=True, exist_ok=True)
    # error correction M, so it still scans with the ink spread of a press
    segno.make(url, error="m").save(str(out), scale=16, border=2,
                                    dark="#111111", light=None)
    return out_rel


def resolve_geometry(issue: dict) -> dict:
    """Trim, bleed and margins from issue.yaml, defaulting to the verified
    Mixam spec. Everything downstream — CSS, preflight, the Mixam numbers —
    reads these, so a different trim size is an issue.yaml edit only."""
    d = DEFAULT_GEOMETRY
    trim = {**d["trim"], **(issue.get("trim") or {})}
    margins = {**d["margins_pt"], **(issue.get("margins_pt") or {})}
    bleed = float(issue.get("bleed_pt", d["bleed_pt"]))
    tw, th = float(trim["width_pt"]), float(trim["height_pt"])
    return {
        "trim_w": tw,
        "trim_h": th,
        "bleed": bleed,
        "quiet": float(issue.get("quiet_pt", d["quiet_pt"])),
        "margin_top": float(margins["top"]),
        "margin_bottom": float(margins["bottom"]),
        "margin_inside": float(margins["inside"]),
        "margin_outside": float(margins["outside"]),
        "media_w": tw + 2 * bleed,
        "media_h": th + 2 * bleed,
        # live text column, and the height the contents page is sized to
        "column_w": tw - float(margins["inside"]) - float(margins["outside"]),
        "content_h": th - float(margins["top"]) - float(margins["bottom"]),
    }


def load_issue(issue_dir: Path) -> dict:
    path = issue_dir / "issue.yaml"
    if not path.exists():
        raise ContentError(f"no issue.yaml in {issue_dir}")
    issue = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    issue["dir"] = issue_dir

    art = (issue.get("mark") or {}).get("image")
    if not art:
        raise ContentError(
            "issue.yaml: mark.image is required. The SQ wordmark is always "
            "supplied artwork — it is never set in type.")
    if not (issue_dir / art).exists():
        raise ContentError(f"issue.yaml: mark artwork not found: {art}")
    issue["mark"]["ink_image"] = derive_mark_variant(issue_dir, art)
    issue["mark"]["shadow_image"] = derive_mark_shadow(issue_dir, art)
    issue["mark"]["shadow_image_back"] = derive_mark_shadow(
        issue_dir, art, mark_alpha=0.55, suffix="-back")

    for key in ("cover", "back_cover"):
        if not (issue.get(key) or {}).get("image"):
            raise ContentError(f"issue.yaml: {key}.image is required")

    about = issue.get("about")
    if about and about.get("pdf_url"):
        about["qr_image"] = derive_qr(issue_dir, about["pdf_url"])

    issue["geometry"] = resolve_geometry(issue)
    issue["articles"] = [parse_article(issue_dir / a)
                         for a in (issue.get("articles") or [])]
    return issue


def fmt_date(d) -> str:
    return d.strftime("%b %-d %Y") if hasattr(d, "strftime") else str(d)
