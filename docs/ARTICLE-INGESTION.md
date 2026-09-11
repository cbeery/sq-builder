# Getting an article into an issue

Articles are reprinted from the web. The usual sources are paywalled or
JS-rendered, so nothing can be fetched — the words and pictures have to
come out of a browser by hand. This is the note on how, and on why one
route is much better than the others.

The short version: **paste into TextEdit, save as RTFD, hand over the
bundle.** It carries the photographs. Nothing else does.

---

## Why RTFD

A browser copy puts two things on the clipboard: text, and references to
the images. Paste it somewhere that only understands text and the
pictures are gone. Paste it into TextEdit as rich text and they are
saved alongside — as real files, at the size the page served them.

Measured on the Mike Trout piece for Fall 2026:

| Route | Words | Photographs |
|---|---|---|
| `pbpaste` to a text file | 7,358 | none |
| RTFD bundle | 7,375 | **10 usable** |

Nine of that article's eleven figures were filled from the bundle in one
pass. Sourcing them any other way is an afternoon of right-clicking.

## Making one

1. Open the article. Let it load fully — lazy-loaded images further down
   the page are not on the clipboard until they have been displayed, so
   **scroll to the bottom first.**
2. Select all, copy.
3. Open TextEdit, **Format → Make Rich Text**, paste.
4. Save. TextEdit writes a `.rtfd` when the document has attachments —
   it is a directory, not a file, and the Finder shows it as one item.
5. Hand over the path.

## What is inside

A `.rtfd` is a plain directory:

```
trout.rtf.rtfd/
  TXT.rtf                    the article text and layout
  e5974b24-….jpg             the images, named however the page named them
  1__#$!@%!#__i.jpg
  2__#$!@%!#__i.png
  …
```

The attachment names are meaningless — they come from the source page,
not from the content. Order and identity have to be recovered.

## Getting the text out

```bash
textutil -convert txt -stdout TXT.rtf
```

**This is the better source of text, not just of pictures.** `textutil`
returns valid UTF-8. `pbpaste` does not reliably: the Fall 2026 Trout
paste came back as Mac OS Roman, where `0x8E` is an e-acute, so
"Pokémon" arrived as bytes Python could not decode. `sq add` repairs
that (`decode_paste`), but the RTFD route never has the problem.

Neither route carries smart quotes — the text arrives with straight
apostrophes either way, and `typographic()` curls them at parse time.

## Getting the images out

Three things have to be worked out, and only the first is automatic.

**Order.** The attachments appear in `TXT.rtf` in document order, so
scanning the RTF for filenames and keeping first appearances gives the
sequence the page used:

```python
names, seen = [], set()
for n in re.findall(r"([0-9a-zA-Z_#$!@%\-]+\.(?:jpg|png))", rtf):
    if n not in seen:
        seen.add(n); names.append(n)
```

**Chrome.** A bundle contains the site's furniture as well as its
photographs — avatars, logos, share icons. On the Trout article, 19
attachments were referenced and only 10 were article photographs; the
other nine were 80×80 and 130×130. A width threshold separates them
cleanly, because no real photograph on these pages is under 1000px.

**Identity.** Which photograph goes with which caption is the part that
still wants a human. Document order is a good first guess and the
credits are a strong second signal — two credits on one caption means a
composite, `Bettmann` or `Getty` means archival, a staff photographer's
name means the recent shoot. Match them, then look at the proof.

## Resolution, and what it means for placement

Bundle images come at whatever width the page served, which is usually
around 1140px. That is:

- **214 ppi** across the full column — a preflight WARN
- **486 ppi** floated at 44% — comfortably fine

So photographs from a bundle usually want floating rather than full
width, and alternating them left and right reads better than a column
of pictures down one edge anyway. Preflight reports the effective figure
at placed size, so let it decide rather than guessing.

## What is still manual

`sq add` takes `--paste` and `--url`. There is no `--rtfd` yet, so the
images are currently extracted by hand: read the order out of the RTF,
drop the photographs into `images/`, and write the paths into the figure
lines. Worth automating before an issue with four articles in it.

## The clipboard route

Still fine when an article has no pictures worth keeping, or when the
bundle is inconvenient:

```bash
pbpaste | sq add 2027-spring --paste - --url https://…
```

`--url` is worth passing even for a paywalled source: the page metadata
usually fills in the title, author, date and publication even when the
body will not come.

## Either way, the frontmatter is yours

The bio is written by hand, every time — never scraped, never inferred.
`sq add` emits `bio: # TODO` and preflight fails on it. Pull quotes are
an editorial choice too: these sources do not mark them in a way a paste
preserves, so nothing detects them for you.
