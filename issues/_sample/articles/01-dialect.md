---
title: Every Construct in the Dialect
dek: A worked example of SQ Markdown, kept in the repo so it cannot drift from the parser
author: The Build
publication: Stan Quarterly
date: 2026-09-10
url: https://github.com/cbeery/sq
bio: The Build is what turns a folder of Markdown into a print-ready PDF. It has no opinions, only a stylesheet.
---

<!-- Comments like this one are dropped at parse time. They never reach the page. -->

@@ {sc}THIS ARTICLE EXISTS{/sc} to exercise the dialect. Every construct the parser understands appears somewhere below, so that if one of them quietly stops working, the test suite notices before an issue does. The first paragraph of an article gets a drop cap automatically; any later paragraph can ask for one with `@@`.

Ordinary paragraphs need no markup. Hard-wrapped lines in the source are collapsed into one line, so you can wrap the Markdown however you like without it showing up in the PDF.

Inline, there is *emphasis* and there is **strong**, and nothing else. That is deliberate: every construct has to map to something the stylesheet actually styles, and a dialect that stays small is a dialect that keeps working.

Punctuation is converted at parse time, so you can type ASCII and get typography. Straight quotes become "curly ones", apostrophes in words like don't and the '90s come out right, `--` becomes an en dash for ranges like 1994--1996, `---` becomes an em dash, and three dots become an ellipsis...

## Subheads

A line beginning with `##` is a section subhead. The stylesheet keeps it with the paragraph that follows, so a subhead never strands itself at the foot of a page.

A figure's alt text can carry a photo credit after a ` | `. The credit is metadata about the image rather than part of what the caption says, so it is set on its own line in lighter type. Pasted web content usually has both, and `sq add` splits them automatically.

![A full-column figure. The caption sits below the image in small bold condensed type, and the whole figure avoids breaking across a page. | Photo: placeholder art](images/plate-column.jpg)

![A figure floated right at 44% of the column. Prose wraps around it and, once the image ends, under it — the behaviour that ruled out Typst as the layout engine.](images/plate-right.jpg){.right}

![The same thing floated left. Alternating sides down a long article stops the pictures stacking into a column against one edge. | Photo: placeholder art](images/plate-right.jpg){.left}

Text set beside a floated figure flows around it and then closes up underneath, which is the ordinary magazine behaviour and is harder to get than it looks. The byline card on the opening page of every article works the same way. Keep writing here so there is enough copy to actually wrap past the bottom edge of the image and demonstrate the point properly, rather than stopping while the float is still in play.

> A pull quote is a line beginning with a greater-than sign, set larger and centred with hairline rules above and below.
> -- With an attribution line

***

The three asterisks above are a section-break ornament, for when a subhead would be too heavy a transition.

> A pull quote does not need an attribution. Leave the second line off and the rule closes up on its own.

## Tables

Tables use the usual pipe syntax. A `|+` line before the header adds a title bar.

|+ The Five Faces, and What They Set
| Role | Face | Variable |
|:---|:---|:---|
| Headline | Mazzard H Black | `--display-face` |
| Subhead | Mazzard H ExtraBold | `--display-alt` |
| Body | Charter | `--body-face` |
| Furniture | Avenir Next | `--ui-face` |
| Captions and tables | Avenir Next Condensed | `--cond-face` |

The separator row carries the alignment: `:---` left, `:---:` centre, `---:` right. Numeric columns generally want the right, so the digits line up. A literal pipe inside a cell is escaped with a backslash.

|+ Alignment, and an Escaped Pipe
| Left | Centred | Right | Escaped |
|:---|:---:|---:|:---:|
| Trim width | pt | 481.68 | 6.69 \| 170 |
| Trim height | pt | 737.28 | 10.24 \| 260 |
| Bleed | pt | 9.00 | 0.125 \| 3.175 |
| Media width | pt | 499.68 | 6.94 \| 176 |

The title bar is optional. Without `|+`, a table simply begins at its header row.

| Check | What it catches |
|---|---|
| Effective PPI | art that looks fine on screen and prints soft |
| Page count | a total that is not a multiple of four |
| Media and trim boxes | a file the printer will reject or silently fudge |
| Font embedding | a face the engine substituted without saying so |
| Colour glyphs | emoji, which are unreliable on press |
| TODO placeholders | an issue reaching the printer half-written |

A table longer than the space left on the page breaks across it, repeating the header row rather than orphaning the body, and no single row is ever split down the middle.

![A full-bleed image page. The art runs past the trim on all four sides and the caption reverses out over a scrim, because WeasyPrint has no text-shadow.](images/plate-full.jpg){.full}

## What is deliberately missing

There is no syntax for columns, no nested lists, no footnotes, no inline images, and no way to set a colour or a size from the Markdown. All of that lives in the stylesheet, where a decision gets made once and applies to every issue, instead of being retyped into each article and drifting apart over a few years.
