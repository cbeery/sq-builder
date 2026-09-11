"""Markdown dialect and issue-loading tests.

The dialect is deliberately small — every construct has to map to
something template/sq.css styles — so this covers all of it.
"""

import pytest

from sq.content import (ContentError, parse_article, parse_blocks,
                        resolve_geometry, typographic)
from sq.render import inline


# --- typography ------------------------------------------------------------

@pytest.mark.parametrize("src,want", [
    ('He said "hi".', 'He said “hi”.'),
    ("It's fine.", "It’s fine."),
    ("the '90s", "the ’90s"),
    ("'Tis and 'til", "’Tis and ’til"),
    ("a -- b", "a – b"),
    ("a---b", "a—b"),
    ("wait...", "wait…"),
    ("'quoted'", "‘quoted’"),
    ('"Yes," she said.', '“Yes,” she said.'),
    ("2014--2016", "2014–2016"),
])
def test_typographic(src, want):
    assert typographic(src) == want


def test_typographic_leaves_real_punctuation_alone():
    already = "It’s “done” already—really…"
    assert typographic(already) == already


# --- dialect ---------------------------------------------------------------

def test_paragraph_and_dropcap():
    b = parse_blocks("@@ First para.\n\nSecond para.")
    assert [x["type"] for x in b] == ["para", "para"]
    assert b[0]["dropcap"] is True
    assert b[1]["dropcap"] is False


def test_hard_wrapped_paragraph_collapses():
    assert parse_blocks("one\ntwo\nthree")[0]["text"] == "one two three"


def test_subhead():
    b = parse_blocks("## A Heading")
    assert b[0] == {"type": "subhead", "text": "A Heading"}


def test_ornament():
    assert parse_blocks("***")[0]["type"] == "ornament"
    assert parse_blocks("*****")[0]["type"] == "ornament"


def test_comments_are_dropped():
    """`sq add` leaves <!-- REVIEW --> notes for the editor. They must
    never reach the page."""
    b = parse_blocks("<!-- REVIEW: check this -->\n\nReal text.")
    assert [x["type"] for x in b] == ["para"]
    assert b[0]["text"] == "Real text."


@pytest.mark.parametrize("src,cls", [
    ("![Cap](images/x.jpg)", ""),
    ("![Cap](images/x.jpg){.left}", "left"),
    ("![Cap](images/x.jpg){.right}", "right"),
    ("![Cap](images/x.jpg){.full}", "full"),
])
def test_figures(src, cls):
    b = parse_blocks(src)[0]
    assert b["type"] == "figure"
    assert b["src"] == "images/x.jpg"
    assert b["caption"] == "Cap"
    assert b["float"] == cls


def test_unknown_figure_class_is_an_error():
    with pytest.raises(ContentError, match="unknown figure class"):
        parse_blocks("![Cap](images/x.jpg){.centre}")


def test_pullquote_with_attribution():
    b = parse_blocks("> Something quotable.\n> -- Ivan Drury")[0]
    assert b["type"] == "pullquote"
    assert b["text"] == "Something quotable."
    assert b["attrib"] == "Ivan Drury"


def test_pullquote_without_attribution():
    assert parse_blocks("> Just the quote.")[0]["attrib"] == ""


# --- inline emphasis (renderer side) ---------------------------------------

@pytest.mark.parametrize("src,want", [
    ("plain", "plain"),
    ("*em*", "<em>em</em>"),
    ("**strong**", "<strong>strong</strong>"),
    ("a *b* and **c**", "a <em>b</em> and <strong>c</strong>"),
    ("{sc}BY THE TIME{/sc} he left",
     '<span class="sc">BY THE TIME</span> he left'),
    ("5 * 3 and 2 * 4", "5 * 3 and 2 * 4"),          # bare stars survive
    ("<script>", "&lt;script&gt;"),                   # still escaped
])
def test_inline(src, want):
    assert inline(src) == want


# --- frontmatter -----------------------------------------------------------

GOOD = """---
title: A Title
dek: A dek
author: A Person
publication: Somewhere
date: 2026-01-01
url: https://example.com/x
bio: A bio.
---

@@ Body text.
"""


def write(tmp_path, text, name="01-x.md"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_parse_article(tmp_path):
    art = parse_article(write(tmp_path, GOOD))
    assert art["title"] == "A Title"
    assert art["slug"] == "01-x"
    assert art["blocks"][0]["dropcap"] is True


def test_absent_field_names_the_file_and_the_field(tmp_path):
    bad = GOOD.replace("author: A Person\n", "")
    with pytest.raises(ContentError, match=r"01-x\.md.*no author field"):
        parse_article(write(tmp_path, bad))


def test_dek_is_optional(tmp_path):
    ok = GOOD.replace("dek: A dek\n", "")
    assert parse_article(write(tmp_path, ok))["dek"] == ""


@pytest.mark.parametrize("line", ["bio: # TODO", "bio:", 'bio: ""'])
def test_todo_bio_builds_but_is_left_for_preflight(tmp_path, line):
    """`sq add` emits `bio: # TODO`, which YAML reads as a comment and so
    parses as null. That must still build, so the layout can be seen —
    preflight is what refuses to let it reach Mixam."""
    art = parse_article(write(tmp_path, GOOD.replace("bio: A bio.", line)))
    assert "TODO" in str(art["bio"])


def test_no_frontmatter(tmp_path):
    with pytest.raises(ContentError, match="missing YAML frontmatter"):
        parse_article(write(tmp_path, "just text"))


# --- geometry --------------------------------------------------------------

def test_geometry_defaults_to_the_verified_mixam_spec():
    g = resolve_geometry({})
    assert (g["trim_w"], g["trim_h"]) == (481.68, 737.28)
    assert g["bleed"] == 9.0
    assert (g["media_w"], g["media_h"]) == (499.68, 755.28)
    assert g["column_w"] == 481.68 - 54 - 44
    assert g["content_h"] == 737.28 - 46 - 42


def test_geometry_is_overridable_from_issue_yaml():
    """Changing the trim size must be an issue.yaml edit and nothing
    else — no CSS, no Python."""
    g = resolve_geometry({"trim": {"width_pt": 400, "height_pt": 600},
                          "bleed_pt": 12,
                          "margins_pt": {"inside": 60}})
    assert (g["media_w"], g["media_h"]) == (424, 624)
    assert g["margin_inside"] == 60
    assert g["margin_outside"] == 44          # default survives
    assert g["column_w"] == 400 - 60 - 44


# --- tables ----------------------------------------------------------------

SIMPLE = """| Year | Event |
|---|---|
| 1994 | Rangers win the Stanley Cup |
| 2015 | A bat flip in the ninth |"""


def test_table_basics():
    b = parse_blocks(SIMPLE)[0]
    assert b["type"] == "table"
    assert b["title"] == ""
    assert b["header"] == ["Year", "Event"]
    assert b["align"] == ["left", "left"]
    assert b["rows"] == [["1994", "Rangers win the Stanley Cup"],
                         ["2015", "A bat flip in the ninth"]]


def test_table_title():
    b = parse_blocks("|+ Halloway's Longest Innings\n" + SIMPLE)[0]
    assert b["title"] == "Halloway’s Longest Innings"   # typographic
    assert b["header"] == ["Year", "Event"]


@pytest.mark.parametrize("sep,want", [
    ("|---|---|---|", ["left", "left", "left"]),
    ("|:---|:---:|---:|", ["left", "center", "right"]),
    ("| :-: | -: | :- |", ["center", "right", "left"]),
])
def test_table_alignment(sep, want):
    src = f"| a | b | c |\n{sep}\n| 1 | 2 | 3 |"
    assert parse_blocks(src)[0]["align"] == want


def test_table_cells_get_typographic_treatment():
    b = parse_blocks("| Note |\n|---|\n| It's a 1994--1995 \"run\" |")[0]
    assert b["rows"][0][0] == "It’s a 1994–1995 “run”"


def test_table_escaped_pipe():
    b = parse_blocks(r"| Sign |" "\n|---|\n" r"| a \| b |")[0]
    assert b["rows"][0] == ["a | b"]


def test_table_without_separator_is_an_error():
    with pytest.raises(ContentError, match="no separator row"):
        parse_blocks("| a | b |\n| 1 | 2 |")


def test_table_with_ragged_row_names_the_row():
    src = "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 |"
    with pytest.raises(ContentError, match="row 4 has 1 cells"):
        parse_blocks(src)


def test_table_with_no_body_is_an_error():
    with pytest.raises(ContentError, match="no body rows"):
        parse_blocks("| a | b |\n|---|---|")


def test_table_separator_must_follow_the_header():
    src = "| a | b |\n| 1 | 2 |\n|---|---|"
    with pytest.raises(ContentError, match="must come directly after"):
        parse_blocks(src)


# --- figure credits --------------------------------------------------------

@pytest.mark.parametrize("alt,caption,credit", [
    ("A caption | Jessica Chou for ESPN", "A caption", "Jessica Chou for ESPN"),
    ("Just a caption", "Just a caption", ""),
    # splits on the LAST separator, so a caption may contain one
    ("Has a | inside | Courtesy of Prep Owl", "Has a | inside",
     "Courtesy of Prep Owl"),
    (r"Escaped \| pipe", "Escaped | pipe", ""),
    ("", "", ""),
])
def test_figure_credit_is_its_own_field(alt, caption, credit):
    b = parse_blocks(f"![{alt}](images/x.jpg)")[0]
    assert b["caption"] == caption
    assert b["credit"] == credit


def test_credit_gets_typographic_treatment():
    b = parse_blocks("![Cap | Courtesy of the Halloway family's archive]"
                     "(images/x.jpg)")[0]
    assert b["credit"] == "Courtesy of the Halloway family’s archive"


def test_credit_survives_a_float_class():
    b = parse_blocks("![Cap | Getty](images/x.jpg){.right}")[0]
    assert (b["credit"], b["float"]) == ("Getty", "right")
