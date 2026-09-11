# sq-builder

The build pipeline for **Stan Quarterly**, a print magazine compiled four
times a year for one reader — my dad. Markdown in, a Mixam-ready PDF out.

This repository is the machinery: the scripts, one stylesheet, and a
worked sample issue. The words and photographs live in a separate private
repository, because they are reprinted from the web and are not mine to
hand out.

It is not a general-purpose tool. The trim size is one printer's spec and
the fonts are ones I happen to own. It is here because the approach might
be useful to someone doing something similar, not because it will run
your magazine unchanged.

## What it does

```bash
sq new 2027-spring          # scaffold an issue
sq add 2027-spring --paste - --url https://...   # ingest an article
sq build 2027-spring        # render the print PDF, then preflight it
sq preflight 2027-spring    # the gate before upload; non-zero on FAIL
sq proof 2027-spring        # same, with crop marks, for reading on screen
sq doctor                   # are the fonts actually resolving?
sq drill                    # a throwaway issue to practise on
```

Try it on the bundled sample:

```bash
make setup
sq build _sample && open out/SQ_Sample_*.pdf
```

That produces a complete twelve-page issue — covers, contents, every
construct in the dialect, an about page — from synthetic placeholder art.

## The interesting parts

**Preflight is the point.** Print failures are quiet ones: a photograph
that looks fine on screen and prints soft, a font the engine substituted
without saying so, a page count that costs a reprint. `sq preflight`
measures the effective resolution of every image *at its placed size*,
verifies every font actually embedded, checks the media and trim boxes,
and refuses the issue if anything is still a placeholder.

**Layout lives in one stylesheet.** `template/sq.css` holds every visual
decision; the Python holds none. Trim, bleed and margins come from the
issue's own settings file and fill `template/geometry.css.in`, so
changing the page size is one edit and touches no code.

**A few things CSS could not do**, and where the build steps in:

- WeasyPrint reserves no advance width for a floated `::first-letter`, so
  drop caps are a real span the renderer emits
- Floats are laid out with `page_is_empty=True`, so `break-inside: avoid`
  cannot hold a figure together — the build detects a photograph that has
  been split from its caption and moves it, re-rendering until clean
- There is no `text-shadow` and no `filter`, so the wordmark's drop
  shadow is composited from its alpha channel at build time

## Layout

```
sq/              content.py  ingest.py  render.py  preflight.py  cli.py
template/        sq.css, and the geometry filled from the issue settings
issues/_sample/  a worked example of every construct
docs/            the full build spec, and the printer runbook
tests/           the parser, the paste cleaner, and end-to-end renders
```

Content is found by looking outward: `SQ_ISSUES` if set, otherwise an
`issues/` directory beside wherever you ran the command, otherwise the
bundled sample. So the private content repository keeps its own
`issues/`, installs this one, and `sq build` works from there.

## Requirements

Python 3.12+, and on macOS the native libraries WeasyPrint wraps:

```bash
brew install pango gdk-pixbuf libffi
```

The five type roles are declared as CSS custom properties, so swapping in
fonts you own is one line each. `sq doctor` will tell you what actually
resolved, which matters because substitution is silent.

## Tests

```bash
make test
```

The paste cleaner's fixtures are synthetic — invented articles wrapped in
real junk: reaction counts, recirculation modules, trailing photo
credits, small-caps section openers. The cleaner does not care what the
prose says, only what shape the noise around it is.
