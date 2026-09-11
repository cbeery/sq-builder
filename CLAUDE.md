# CLAUDE.md — sq-builder

Project rules. Read `docs/BUILD-SPEC.md` for the full brief before
writing code; this file is the short list of things that must not drift.

## What this is

The build pipeline for Stan Quarterly: a one-off print magazine, three or
four articles per issue, four issues a year, compiled for one reader.
Articles are reprinted from the web. Output is a print-ready PDF uploaded
to Mixam.

This repository holds only the machinery and a synthetic sample issue.
The words and photographs live in a separate private repository. **No
reprinted article text or photography belongs in here** — the paste
fixtures are invented articles carrying real junk patterns, and they must
stay that way.

## Hard rules

- **Trim is 481.68 × 737.28 pt** (6.69 × 10.24 in / 170 × 260 mm) with
  **9 pt bleed**, giving a 499.68 × 755.28 pt media box. Verified against
  a printed issue. Don't change these without a new Mixam order spec.
- **Page count must be a multiple of 4.** The build pads before the
  inside-back-cover blank, so the last two leaves are always that blank
  and the back cover.
- **Every issue has the same fixed shape.** Front cover; blank inside it;
  contents; blank behind the contents leaf; articles; padding; the about
  page; blank; blank inside the back cover; back cover.
- **Numbering starts at the contents.** It is the third leaf but page 1,
  so the first article opens on PDF page 5 carrying folio 3 — the folio
  is always the PDF page less two. Covers, blanks and the contents print
  none. WeasyPrint only honours a page-counter reset on a named `@page`;
  `counter-reset: page` on the element is silently ignored.
- **The about page is always the last real page.** A right-hand page,
  with a blank verso behind it, then the blank inside the back cover,
  then the back cover — page `T-3`, always one more than a multiple of
  four. Never on the inside back cover. The build pads forward to land it
  there and the blanks that fall out are fine.
- **A photograph and its caption never separate across a page.** CSS
  cannot enforce this: floats are laid out with `page_is_empty=True`, so
  `break-inside: avoid` has nowhere to push a float and is ignored. The
  build detects the split and moves the figure, re-rendering until clean.
- **No QR codes, with exactly one exception.** An early issue put them in
  every byline card; that is discontinued and must not return, in byline
  cards or anywhere in the articles. The single permitted QR is on the
  about page, pointing at an online copy, and only when `about.pdf_url`
  is set.
- **The SQ wordmark is supplied artwork, never set in type.** It is
  Mazzard H Black with a distinctive angled Q tail; a substitute grotesque
  is visibly wrong. `mark.image` is required — missing artwork is a hard
  build error. It appears on both covers and on the contents page; the
  dark and drop-shadowed variants are derived from the artwork's alpha at
  build time, not supplied separately.
- **One finished image per cover, always full bleed.** The art fills the
  page and runs off all four edges — never a band, an inset, or a photo
  on a colour field. If cover art is too low-resolution the answer is
  different art, never a layout that uses less of it and never an
  upscale. If none exists, a soft full-bleed cover is preferred to any
  other treatment: set `cover.accept_low_resolution: true` so preflight
  reports an acknowledged WARN rather than a standing FAIL nobody reads.
- **Author bios are written by hand.** Never scraped, never inferred.
  `sq add` emits `bio: # TODO` and preflight FAILs on any `# TODO`.
- **Ingestion is paste-first.** The usual sources are paywalled or
  JS-rendered and cannot be fetched. `--url` is useful for metadata only.

## Fonts

Three roles in use, three families. Declared as CSS custom properties so
a swap is one line.

| Role | Face | Variable |
|---|---|---|
| Cover stamps only | Mazzard H Black | `--display-face` |
| Body, deks, bios, drop caps | Charter | `--body-face` |
| Everything else | Avenir Next Condensed | `--cond-face` |
| — unused — | Mazzard H ExtraBold | `--display-alt` |
| — unused — | Avenir Next | `--ui-face` |

`--cond-face` carries article titles, subheads, the contents page, pull
quotes, byline cards, folios, captions, credits and tables.

Font substitution fails silently — the engine swaps without warning and
the PDF looks plausible until it prints wrong. Preflight verifies
embedding; `sq doctor` reports what each role actually resolved to.

## Engine notes

WeasyPrint, chosen over Typst because the design floats byline cards and
images with text wrapping around *and under* them, which Typst can't do.
Quirks worked around in `template/sq.css`, all commented in place:

- `height: 100%` does not resolve against the page box
- flex `margin-top: auto` does not push a child to the bottom
- a floated `::first-letter` gets no advance width, so the drop cap is a
  real span the renderer emits
- `text-transform` inherits into `::first-letter`
- there is no `text-shadow` and no `filter`
- `overflow: hidden` is dropped below a float, not set beside it
- crop marks are drawn inside the bleed, not outside it

## Before every upload

`sq preflight` must show zero FAILs. It checks image PPI **at placed
size** (cover art measured after cover-fill scaling), page count, the
media/trim/bleed boxes, font embedding, colour glyphs, missing images and
TODOs. It also prints the number to type into Mixam's calculator, which
is **not** the PDF's page count when a separate cover is ordered, and
warns once the issue outgrows saddle stitching.
