# Stan Quarterly — build spec

Build me a repeatable pipeline that turns a folder of Markdown into a
print-ready PDF for Mixam. This replaces an Apple Pages workflow.

Context: SQ is a one-off print magazine, ~40 pages, four issues a year,
compiled for one reader. Articles are reprinted from the web. Issue 1
(Summer 2026) was laid out by hand in Pages; issue 2 is Fall 2026.

A working prototype exists — see "Starting point" at the bottom. Start from
it rather than greenfield.

---

## 1. Stack

- **Python 3.12+**, `uv` or a plain venv.
- **WeasyPrint** for layout (CSS Paged Media). Chosen over Typst because SQ's
  design floats byline cards and images with text wrapping around and under
  them; Typst has no text-wrap-around. WeasyPrint also emits a correct
  TrimBox/BleedBox unprompted and supports `marks: crop cross`.
- **PyYAML**, **Pillow**, **pypdf**.
- **trafilatura** for URL extraction.
- A `justfile` (or Makefile) wrapping the commands.

Single CLI entry point, `sq`, via `[project.scripts]`.

---

## 2. Repo layout

```
sq/
  issues/
    2026-fall/
      issue.yaml
      articles/
        01-<slug>.md
        02-<slug>.md
      images/
      generated/          # derived assets — gitignored
  template/
    sq.css                # ALL layout decisions live here
    fonts/
  sq/                     # the package
    __init__.py
    cli.py
    content.py            # Markdown dialect parser
    ingest.py             # URL + paste ingestion
    render.py             # HTML emit + WeasyPrint
    preflight.py
  out/                    # gitignored
  justfile
  README.md
```

One `issue.yaml` per issue; issues are independent folders so old ones stay
reproducible.

---

## 3. Print geometry — these numbers are verified, do not change them

Taken from the Summer 2026 PDF as ordered from Mixam ("Standard" magazine).

| Thing | Value |
|---|---|
| Trim | 481.68 × 737.28 pt (6.69 × 10.24 in / 170 × 260 mm) |
| Bleed | 9 pt (0.125 in) all four edges — Mixam requirement |
| Media box | 499.68 × 755.28 pt |
| Quiet area / gutter | 18 pt (0.25 in) — Mixam saddle-stitch requirement |
| Margins | top 46, bottom 42, inside 54, outside 44 (pt, from trim) |
| Page count | MUST be a multiple of 4 |
| Colour | RGB is acceptable; Mixam converts. Do not attempt CMYK. |
| Image resolution | 150 dpi floor, 300 dpi target, at placed size |

Trim/bleed/margins come from `issue.yaml`, defaulting to the above, so a
future issue can be ordered at a different size without editing CSS.

Mirror the gutter: `@page :left` swaps inside/outside margins and moves the
folio to the opposite corner.

---

## 4. Content model

### `issue.yaml`

```yaml
title: Stan Quarterly
abbr: SQ
issue: Fall 2026
subtitle: Compiled by Curt, for Stan
colophon: All content reprinted without permission. Oh well.

# The SQ wordmark is ALWAYS supplied artwork, never set in type.
mark:
  image: images/sq-mark.png   # transparent PNG, required

# ONE image per cover, always. Never a composite assembled by the build.
cover:
  image: images/cover.jpg
  focus: center             # crop anchor: center|top|bottom|left|right|"50% 30%"
  stamp: Fall 2026          # bottom-left overlay text
back_cover:
  image: images/back-cover.jpg
  focus: center
  stamp: Compiled by Curt, for Stan

trim:  { width_pt: 481.68, height_pt: 737.28 }
bleed_pt: 9.0
quiet_pt: 18.0

theme:
  accent: "#2FC79A"
  ink:    "#111111"
  muted:  "#6E6E6E"
  rule:   "#D8D8D8"

articles:
  - articles/01-....md
  - articles/02-....md
```

Article order in this list is the order in the magazine and the TOC.

### Article frontmatter

```yaml
---
title: The Longest Afternoon at Kestrel Park
dek: A twenty-year-old infielder, a season handed to him, and a club standing back
author: Dana Whitfield
publication: The Wire
date: 2026-03-03
url: https://example.com/2026/03/03/...
bio: Dana Whitfield writes about the minor leagues for ...
---
```

All fields required except `dek`. Fail the build with a clear message naming
the file and the missing field — never silently render a half-populated
byline.

`bio` is written by hand, every time. It is not scraped and not inferred:
paywalled sources cut off before the bio, and at roughly three articles per
issue, four issues a year, it is a dozen short paragraphs annually. `sq add`
always emits `bio: # TODO`, and **preflight FAILs on any `# TODO` left in
frontmatter** so an issue can't reach Mixam with a placeholder in it.

### SQ Markdown dialect

Keep it small. Every construct must map to something the template styles.

| Syntax | Renders as |
|---|---|
| ordinary paragraph | body paragraph |
| `@@ text...` | paragraph with a drop cap (first paragraph of an article gets one automatically) |
| `## Heading` | section subhead |
| `![Caption](images/x.jpg)` | full-column figure with caption below |
| `![Caption](images/x.jpg){.right}` | figure floated right at ~44% column, text wraps |
| `![Caption](images/x.jpg){.full}` | full-bleed image page |
| `> quote text` | pull quote, rules above and below, centred |
| `> quote` + `> -- Name` | pull quote with attribution |
| `***` | section break ornament |

Inline: `*em*`, `**strong**` only. Convert straight quotes and `--`/`---` to
typographic equivalents at parse time.

Parser must produce a neutral block list (`{"type": "para", ...}`) that the
renderer consumes, so the layout backend stays swappable.

---

## 5. Commands

### `sq new <issue-slug>`
Scaffolds `issues/<slug>/` with a starter `issue.yaml` and empty dirs.

### `sq add --paste <file.txt> --url <URL>`  ← **the primary path**

Most SQ sources (The Ringer, The Atlantic) are paywalled, so the body text
arrives as a manual copy/paste out of the browser. Build and test this path
first; treat it as the normal way an article enters the system, not a
fallback.

Reads plain text (from a file, or stdin if `--paste -`) and:

- splits on blank lines into paragraphs
- collapses hard-wrapped lines within a paragraph into one line
- normalises the mess a browser copy produces: non-breaking spaces, zero-width
  characters, smart-quote variants, soft hyphens, doubled blank lines
- strips reader junk — share/subscribe prompts, "Read more", "Sign in to
  continue", newsletter interstitials, cookie notices, standalone photo
  credits, a byline repeated from the page header, stray timestamps
- detects likely subheads (short standalone lines, no terminal punctuation,
  title-ish casing) and promotes them to `##`, **printing each one for
  confirmation rather than guessing silently**
- detects likely pull quotes (a sentence repeated verbatim elsewhere in the
  body — how most sites mark them) and flags them, since a naive paste
  duplicates that text
- marks the first paragraph `@@` for the drop cap
- writes `articles/NN-<slug>.md` and appends it to `issue.yaml`

**`--url` is still worth passing even for paywalled sources.** Page metadata
(`og:title`, `article:author`, `article:published_time`, `og:site_name`) is
usually served to unauthenticated requests even when the body isn't, so
frontmatter can often be filled automatically while the body comes from the
paste. Fall back to `# TODO` comments for anything it can't determine.

Images can't be copy/pasted, so the paste path leaves `![](...)` placeholders
where it detects a caption-shaped orphan line, and the user drops files into
`images/` and fills the paths.

### `sq add --url <URL>`  (opportunistic)

For the occasional source that isn't paywalled. Same output format. Fetch and
extract with trafilatura, auto-fill frontmatter, download in-article images
into `images/` and insert `![alt](...)` lines using the original
`alt`/`figcaption`.

**If extraction yields under ~400 words, print a loud warning** that the
source is probably paywalled and stop — do not write a stub that looks
complete when it isn't. Tell the user to use `--paste` instead.

Both paths end with a file the user hand-edits. That's expected. The tool
gets it 90% there; it does not need to be perfect. Optimise for "obvious what
still needs fixing" over "looks finished".

### `sq build [issue-slug]`
1. Parse `issue.yaml` and every article.
2. Emit HTML, render with WeasyPrint.
3. Count pages; if not a multiple of 4, insert blank filler pages before the
   back cover and re-render. Blanks carry no folio.
4. Write `out/SQ_<Issue>_<date>.pdf`.
5. Run preflight automatically and print the report.

Must be idempotent and fast enough to run on every save. Add `sq build
--watch`.

### `sq preflight [issue-slug]`
Checks, with OK/WARN/FAIL per line and a non-zero exit on FAIL:
- effective PPI of every image **at its placed size** (not its raw pixel
  count) — FAIL under 150, WARN under 300
- page count is a multiple of 4
- media box == trim + 2×bleed
- TrimBox and BleedBox are declared
- all fonts embedded
- no colour-emoji glyphs anywhere (the Summer issue embedded Apple Color
  Emoji for one character; colour fonts are unreliable in print)
- every article has a `url` in frontmatter
- no image is missing from disk

### `sq proof [issue-slug]`
Same as build but with `marks: crop cross` and a light trim-line overlay, for
checking on screen. Never upload this file.

---

## 6. Layout requirements

All of this belongs in `template/sq.css`. The Python side must contain zero
visual decisions.

**Front cover** — named page, zero margin, image absolutely positioned at
`-9pt` inset and `calc(100% + 18pt)` in both dimensions with `object-fit:
cover` so it fills the bleed, and `object-position` from `focus`. The wordmark image from `mark.image` sits top-right at 100pt wide; the issue
stamp is bottom-left. Both positioned relative to trim, not media.

The wordmark appears in **three** places per issue — front cover, back cover,
and the foot of the contents page — all three drawn from the same artwork
file. Covers use it white; contents needs it dark, and the build recolours it
from the artwork's alpha channel rather than requiring a second file.

**The wordmark is never set in type.** It is drawn in Mazzard H Black with
tight tracking and a distinctive angled Q tail; substituting any other
grotesque is visibly wrong. `mark.image` is required — a missing or absent
file is a hard build error and a preflight FAIL, not a reason to fall back to
web type. Back cover uses the same artwork at 74pt and 55% opacity.

The user always supplies **a single finished image** per cover — never a set
of images for the build to arrange. The build's only jobs are to fill the
bleed, honour the crop anchor, and draw the wordmark and stamp over the top.
Ideal source is ~2082 x 3147 px (6.94 x 10.49 in at 300 ppi). Preflight must
measure cover resolution **after cover-fill scaling**, not against page width,
and warn when more than ~12% of an axis is lost to the crop — a square image
on this trim loses a third of its width, which measuring by width alone
hides.

**Back cover** — identical treatment, smaller and semi-transparent wordmark,
`subtitle` as the bottom-left stamp.

**Contents page** — issue name, "Contents", then one entry per article:
title, then author / publication / date, leader dots, page number, then the
source URL in small grey type. Page numbers come from
`target-counter(attr(href), page)`. Nothing about the TOC is hand-maintained.
Colophon line at the bottom.

**Article opener** — title, dek, then a floated byline card containing
author, publication and date, with the opening paragraph wrapping around and
under it. Drop cap on the first paragraph.

**No QR codes.** Summer 2026 put a QR of the source URL in every byline card.
That is discontinued from Fall 2026 onward and must not be reintroduced. The
`url` stays in frontmatter and prints in the contents listing, but nothing
generates or renders a QR image.

**Running folios** — page number bottom-outside, italic, from page 3 onward.
Suppressed on covers, contents, and filler pages.

**Figures** — caption in small bold type below the image, `break-inside:
avoid`.

**Pull quotes** — hairline rules above and below, centred, larger grey type,
optional attribution line.

**Author bio** — dotted rule, name, then italic bio, at the end of each
article.

---

## 7. Fonts

Four faces, all installed on the production Mac. Roles are taken from how
Summer 2026 actually used them, with Charter added for body text.

| Role | Face | Where |
|---|---|---|
| Headline | **Mazzard H Black** | Article titles, contents heading, cover issue stamp |
| Subhead | **Mazzard H ExtraBold** | Section subheads, author-bio name, "Contents" |
| Body | **Charter** | All article prose, deks, pull quotes |
| Furniture | **Avenir Next** | Byline card, running folios |
| Small furniture | **Avenir Next Condensed** | Figure captions, contents metadata lines, tables |

Declared as CSS custom properties (`--display-face`, `--display-alt`,
`--body-face`, `--ui-face`, `--cond-face`) so a face swap is one line, never a
search-and-replace through the stylesheet.

Reference them by family name and let the system resolve them. Keep
`template/fonts/` plus `@font-face` rules as a fallback so the build is
reproducible on another machine. **Verify embedding in preflight** — the
failure mode is silent: the engine substitutes without warning and the PDF
looks plausibly fine until it prints wrong.

Mazzard's family naming needs checking on the first local run. Foundry
families with many weights are sometimes installed as separate families
("Mazzard H Black") and sometimes as one family with weight variants
("Mazzard H" at weight 900). The stack lists both patterns; confirm which one
resolves and prune the other.

## 8. Definition of done

- `just build` on a fresh clone produces a PDF that passes `sq preflight`
  with zero FAILs.
- Adding a new article is: run `sq add`, edit the frontmatter, run
  `sq build`. No layout files touched.
- Changing the trim size means editing `issue.yaml` only.
- A README that a person who has forgotten everything can follow in three
  months to produce the next issue.

Write tests for the Markdown parser and the paste cleaner — those are where
regressions will actually happen. Layout doesn't need unit tests; preflight
is the test.

---

## Starting point

There's a prototype at `sq-pipeline-prototype.zip` with:

- `build/sqcommon.py` — the dialect parser, roughly the shape `content.py`
  should take
- `build/css/sq.css` — a working stylesheet with the geometry, covers,
  floated byline card, drop caps, TOC leader dots and pull quotes already
  correct
- `build/build_weasy.py` — HTML emit + two-pass page padding
- `build/preflight.py` — the PPI and box checks
- `content/` — two real articles in the dialect, plus images

Refactor the prototype into the package layout above, add the ingestion
commands and the CLI, and fill the gaps — the prototype has no `{.full}`
bleed pages, no section-break ornament, no inline emphasis handling, no
`:left` gutter mirroring worth trusting, and no font embedding story.
