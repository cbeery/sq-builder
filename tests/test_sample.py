"""The sample issue is living documentation, so it has to stay true.

issues/_sample exercises every construct in the dialect. If one of them
silently stops working — the way `text-shadow` was silently ignored, or
the way a floated ::first-letter silently ran text underneath itself —
this is what notices.
"""

from pathlib import Path

import pytest

from sq import preflight
from sq.cli import ISSUES, resolve_issue
from sq.content import load_issue
from sq.render import build

SAMPLE = Path(__file__).resolve().parent.parent / "issues" / "_sample"

# Everything parse_blocks() can emit. A new construct should show up in the
# sample article too, or it is undocumented and untested.
EVERY_BLOCK_TYPE = {"para", "subhead", "figure", "pullquote", "ornament",
                    "table"}


@pytest.fixture(scope="module")
def sample():
    return load_issue(SAMPLE)


def test_sample_uses_every_construct(sample):
    kinds = {b["type"] for art in sample["articles"] for b in art["blocks"]}
    missing = EVERY_BLOCK_TYPE - kinds
    assert not missing, f"the sample no longer demonstrates: {sorted(missing)}"


def test_sample_uses_every_figure_placement(sample):
    placements = {b["float"] for art in sample["articles"]
                  for b in art["blocks"] if b["type"] == "figure"}
    assert placements == {"", "left", "right", "full"}


def test_sample_covers_titled_and_untitled_tables(sample):
    tables = [b for art in sample["articles"] for b in art["blocks"]
              if b["type"] == "table"]
    assert any(t["title"] for t in tables), "no table with a title bar"
    assert any(not t["title"] for t in tables), "no table without one"
    aligns = {a for t in tables for a in t["align"]}
    assert aligns == {"left", "center", "right"}, "not every alignment shown"


def test_sample_builds_and_preflights_clean(tmp_path, capsys):
    """Zero FAILs and zero WARNs. It is a fixture with placeholder art at
    full print resolution, so there is nothing legitimate to warn about —
    which makes any new warning a signal rather than noise."""
    pdf = build(SAMPLE, tmp_path)
    assert preflight.run(SAMPLE, pdf), "sample issue does not preflight clean"
    # the level markers, not the "0 FAIL, 0 WARN" summary line
    report = capsys.readouterr().out
    flagged = [l for l in report.splitlines()
               if "[WARN]" in l or "[FAIL]" in l]
    assert not flagged, "sample no longer preflights clean:\n" + "\n".join(flagged)


def test_sample_is_not_picked_as_the_default_issue():
    """`_`-prefixed directories are fixtures. `sq build` with no argument
    must never reach for one — and in the builder repo, where the sample
    is the only issue there is, it must say so rather than build it."""
    from sq.content import ContentError

    assert resolve_issue("_sample") == SAMPLE
    assert (ISSUES / "_sample").exists()
    try:
        assert resolve_issue(None) != SAMPLE
    except ContentError as exc:
        assert "no issues found" in str(exc)


def test_sample_carries_no_reprinted_content(sample):
    """Fixtures are committed and this repo is private for a reason. The
    sample must stand on its own."""
    art = sample["articles"][0]
    assert art["publication"] == "Stan Quarterly"
    assert "github.com" in art["url"]
