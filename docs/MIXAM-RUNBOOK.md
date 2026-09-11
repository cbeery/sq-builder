# Mixam runbook for Stan Quarterly

Everything between "the PDF is done" and "copies arrive." Written against
Mixam's US site as of September 2026 — their UI changes, so treat the click
paths as a guide and the rules as the durable part.

---

## The one thing that will bite you

**The page count you type into the calculator is not the number of pages in
your PDF.**

Mixam's own words: if your item has a separate cover, don't include the cover
pages in your total — subtract four. A 28-page file gets entered as 24.

So for a 20-page Fall 2026 PDF:

| Order type | What it means | Enter |
|---|---|---|
| **Self-cover** | Cover printed on the same stock as the inside pages | **20** |
| Add Cover (+4 printed pages) | Separate heavier cover stock | 16 |
| Add Cover, inner cover printing = No | Separate cover, insides of it blank | 18 |

Your Summer issue was a 40-page PDF. Whichever of these you picked then, pick
the same one now, or Fall will come back a different object.

`sq preflight` prints all three numbers at the end of every run, so you never
have to do the arithmetic under pressure. Check what you selected last time
before typing.

---

## Order specification

Set these once, then reorder forever.

| Field | Value | Why |
|---|---|---|
| Product | Magazine | Right category for saddle-stitch with a cover |
| Size | Custom, 6.69 × 10.24 in (170 × 260 mm) | Matches the Summer trim exactly |
| Pages | see table above | |
| Binding | Saddle-stitch (staple) | Correct to ~60 pages; Mixam's calculator will force perfect binding if you exceed the staple limit |
| Color | Full color throughout | Your covers are duotone and the interiors have photos |
| Quantity | Whatever you actually need | It's a one-off for one reader — don't let a price break talk you into 25 |

Mixam's calculator switches you from staple to perfect binding automatically
once page count or paper weight crosses the threshold. If that happens
unexpectedly, your issue got longer than you thought — worth noticing rather
than accepting silently, since perfect binding needs a printed spine and
changes the cover artwork.

**Order a free sample pack** before you commit to a paper. Seeing your Summer
issue's stock next to the alternatives beats guessing from a dropdown.

---

## File requirements

All of this is already handled by the build — listed so you can verify rather
than trust.

- **One multi-page PDF**, covers included, in reading order. Mixam accepts
  other formats but prefers a single PDF.
- **0.125 in bleed** on every page, including inners. Already in the file:
  media box 499.68 × 755.28 pt around a 481.68 × 737.28 pt trim.
- **0.25 in quiet area and gutter** for saddle-stitch. Nothing important
  within a quarter inch of the trim or the fold.
- **Images 150–300 dpi at placed size.** Preflight reports the effective
  figure, not the raw pixel count, which is the number that actually matters.
- **Fonts embedded.**
- **CMYK preferred**, RGB accepted and converted. The build outputs RGB.
  Mixam's profile is GRACoL2006_Coated1v2 if you ever want to soft-proof.

Do not upload the `sq proof` output — that one carries crop marks.

---

## Order one: the proof copy, to yourself

Do this with the runbook open. It takes about fifteen minutes.

**Before you start**, open Order History and look at the previous issue.
Write down two things: the **cover option** it was ordered with, and the
**paper**. You need the cover option before you can type a page count,
and it is the single easiest thing to get wrong.

1. **Instant Quote Calculator.** Set:

   | Field | Value |
   |---|---|
   | Product | Magazine |
   | Size | Custom — **6.69 × 10.24 in** (170 × 260 mm) |
   | Pages | **see step 2** |
   | Binding | Saddle-stitch (staple) |
   | Colour | Full colour throughout |
   | Paper | same as last issue |
   | Quantity | **1** |

2. **Pages.** Run `sq preflight` and read the three numbers off the end
   of it. Enter the one matching the cover option you just looked up —
   **not** the number of pages in the PDF, unless the order is
   self-cover. Getting this wrong is the mistake that reprints an issue.

3. Add to cart, continue to the **Artwork** tab.

4. **Upload the one PDF.** The file with neither `_proof` nor `_screen`
   in its name. Covers are included in it; do not upload them separately.

5. **Check every page thumbnail is filled.** A grey one marked "Artwork
   Missing" blocks the proof.

6. **Check the bleed guides.** The uploader draws a blue bleed line and a
   green trim line over your pages. Confirm the cover art actually
   reaches the blue line on both covers.

7. **Preview** — the flipbook. Look for pages in the wrong order, a
   missing spread, a gutter mirrored the wrong way.

8. **PDF Proof.** Click Proof, wait for the checkmark, click again to
   open, then **download it and open in Acrobat** — not the browser —
   with Overprint Preview on.

9. **Delivery address: yourself.**

10. **Confirm.** Cut-off is 4pm CT on workdays; after that the ship date
    moves.

## Order two: Stan's copy

Only after the proof copy has arrived and you have read it. If it showed
anything, fix it, rebuild, and get `sq preflight` back to zero FAILs
first.

1. **Order History → find the proof order → Reorder.** This clones the
   whole specification, so you do not re-derive size, binding, paper or
   the page-count arithmetic.

2. **Replace the PDF** if you changed anything. If you did not, leave it.

3. **Change the delivery address to Stan's.** This is the one Mixam
   themselves flag as the common reorder mistake, and a reorder carries
   the old address forward silently.

4. **Check the page count** if the issue changed length. That is a
   specification change, not just a file swap.

5. Proof, then confirm.

If you reordered pages by dragging thumbnails at any point, un-confirming
can revert them — fix page order in the source and re-upload instead.

## Ordering, step by step

1. **Instant Quote Calculator** — set the spec above, get a price and an
   estimated ship date, add to cart, continue.
2. **Download their template** from the calculator once, for reference. It
   shows bleed, trim, quiet area and gutter for your exact spec. You don't
   need it to lay out, but it's a good sanity check against what the build
   produces.
3. **Artwork tab** — upload the single PDF. Mixam runs its own preflight and
   flags problems. Every page thumbnail must be filled; grey ones marked
   "Artwork Missing" will block the proof.
4. **Check the bleed guides.** The uploader draws a blue bleed line and a
   green trim line over your pages. This is the moment to confirm your cover
   art actually reaches the blue line. Your Summer file had no bleed at all,
   so Mixam either applied a false bleed or the edges got fudged — this time
   the art genuinely extends 9pt past trim, and you should be able to see it.
5. **Preview** — the flipbook view. Good for catching pages in the wrong
   order, a missing spread, a left/right gutter that's mirrored backwards.
6. **PDF Proof** — click Proof, wait for the checkmark, click again to open,
   then **download it and open in Acrobat**, not the browser. Turn on
   Overprint Preview (Edit → Preferences → Page Display → Use Overprint
   Preview → Always). This is the closest you get to seeing the real thing.
7. **Confirm.** Cut-off for confirmed orders is 4pm CT on workdays; confirming
   after that pushes your ship date.

If you need to change something after confirming, you can **un-confirm**,
edit, and re-confirm. Each version needs a print expert's approval, so it
costs you time rather than money. One caveat from their docs: if you manually
reordered pages via the thumbnails, un-confirming can revert them — another
reason to fix page order in the source and re-upload rather than dragging
thumbnails.

---

## Order it twice

Every issue is printed twice, and the first one is a proof:

1. Build the issue and get `sq preflight` to zero FAILs.
2. Order **one copy, delivered to yourself.**
3. Read the physical copy properly when it arrives.
4. Fix whatever it shows, rebuild, then order the copy for Stan.

This is not caution for its own sake. There is a whole category of
problem that no preflight and no on-screen proof can catch, because it
only exists on paper:

- **Colour.** The build outputs RGB and the press is CMYK. Saturated
  single hues move the most, and a cover built around one is exactly the
  case that shifts.
- **Soft images.** Preflight reports effective PPI, but only the print
  tells you whether 125 ppi on a period photograph reads as character or
  as a mistake.
- **The gutter.** Whether the inside margin is genuinely enough once the
  staples are in and the thing does not want to lie flat.
- **Ink density.** Heavy dark pages showing through the leaf behind them.
- **Trim drift.** Where the blade actually fell, against where the art
  assumed it would.

Order the second copy as a **reorder** of the first, so the specification
is cloned rather than re-entered, and change only the delivery address
and the file. See below.

## Making the next issue trivial

**Reorder is the whole trick.** Order History → find Summer 2026 → **Reorder**.
It clones every specification and the uploaded files into a new pending order.
Swap the PDF, adjust nothing else, confirm.

That means you never re-derive the size, binding, paper, or the page-count
arithmetic. Fall becomes: build, preflight, reorder, replace file, proof,
confirm.

Two things to re-check on every reorder, because they're the ones that
silently carry over wrong:

- **Page count**, if the issue got longer or shorter. This is a spec change,
  not just a file swap.
- **Delivery address**, which Mixam explicitly flags as the common reorder
  mistake.

**Keep a note per issue** — order number, page count entered, cover option,
paper, quantity, ship date. Three months is long enough to forget which cover
option you chose, and the whole point of the pipeline is not re-deciding
solved things. Worth a `mixam.md` in each issue folder.

---

## Sanity checklist before every upload

```
sq preflight
```

should show zero FAILs, then confirm by eye:

- [ ] Page count is a multiple of 4
- [ ] Number entered on the calculator matches your cover option, not the raw PDF count
- [ ] Cover art reaches the blue bleed line in the Artwork tab
- [ ] No `# TODO` anywhere — preflight fails on these now
- [ ] All images present, none flagged MISSING
- [ ] Proof downloaded and read in Acrobat with Overprint Preview on
- [ ] Delivery address is right — **yourself for the proof copy, Stan for the real one**

---

## Worth knowing

- **Free sample packs** — order one; useful for choosing paper for Fall.
- **Rewards program** — Mixam runs a points scheme, double points on a first
  order with an account. Marginal at four orders a year, but free.
- **Custom quotes** — if the standard calculator won't do what you want, you
  can email specs and get a price back. Quotes are valid two weeks.
- **Colour will shift.** RGB source, CMYK press. Your Summer cover was a
  green duotone, which is exactly the kind of saturated single-hue that moves
  most between screen and paper. If Fall's cover matters to you, compare the
  printed Summer copy against what you saw on screen and adjust the source
  image, rather than trying to correct it in the pipeline.
