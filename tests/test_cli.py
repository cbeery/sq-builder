"""CLI behaviour: the rehearsal commands and the bits of `sq doctor`
that are worth pinning down."""

import shutil
import time
from argparse import Namespace
from pathlib import Path

import pytest

from sq import cli
from sq.ingest import fetch_html
from sq.render import build

REPO = Path(__file__).resolve().parent.parent


# --- font checking ---------------------------------------------------------

@pytest.mark.parametrize("wanted,got,ok", [
    # Pango names a face by weight and width class, not by its full name,
    # so this is the CORRECT font reporting an unfamiliar name.
    ("Mazzard H Black", "KRCJNX+Mazzard-Heavy-Semi-Condensed", True),
    ("Mazzard H ExtraBold", "DFQIVT+Mazzard-Ultra-Bold-Semi-Condensed", True),
    ("Charter", "RATJMB+Charter", True),
    ("Avenir Next Condensed", "FBPJSG+Avenir-Next-Condensed,-Condensed", True),
    # the failure that matters: the family is gone and a fallback stood in
    ("Mazzard H Black", "ABCDEF+DejaVuSans", False),
    ("Charter", "ABCDEF+LiberationSerif", False),
])
def test_font_matches_tolerates_renaming_but_catches_fallbacks(wanted, got, ok):
    assert cli.font_matches(wanted, got) is ok


# --- network ---------------------------------------------------------------

def test_fetch_gives_up_quickly_rather_than_stalling():
    """The normal path is paste-first, so metadata is a nicety. A slow or
    unreachable URL must not hold up the command — this used to have no
    timeout at all and stalled `sq add` for the better part of a minute."""
    t0 = time.time()
    assert fetch_html("https://10.255.255.1/nope", timeout=2) is None
    assert time.time() - t0 < 6


def test_fetch_swallows_a_malformed_url():
    assert fetch_html("not-a-url-at-all", timeout=2) is None


# --- sq drill --------------------------------------------------------------

@pytest.fixture
def fake_issues(tmp_path, monkeypatch):
    issues = tmp_path / "issues"
    issues.mkdir()
    shutil.copytree(REPO / "issues" / "_sample", issues / "_sample")
    monkeypatch.setattr(cli, "ISSUES", issues)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    return issues


def test_drill_scaffolds_something_that_builds(fake_issues, tmp_path, capsys):
    """The whole point is a practice run that works immediately, so it
    borrows the sample's placeholder artwork rather than asking for art."""
    assert cli.cmd_drill(Namespace(reset=False)) == 0
    drill = fake_issues / cli.DRILL
    assert (drill / "issue.yaml").exists()
    assert (drill / "articles").is_dir()
    assert (drill / "images" / "cover.jpg").exists()

    pdf = build(drill, tmp_path / "out")
    assert pdf.exists()


def test_drill_starts_with_no_articles(fake_issues, capsys):
    cli.cmd_drill(Namespace(reset=False))
    text = (fake_issues / cli.DRILL / "issue.yaml").read_text()
    assert "01-dialect.md" not in text, "carried the sample's article over"
    assert text.rstrip().endswith("articles:")


def test_drill_will_not_clobber_without_reset(fake_issues, capsys):
    cli.cmd_drill(Namespace(reset=False))
    marker = fake_issues / cli.DRILL / "articles" / "mine.md"
    marker.write_text("work in progress")

    cli.cmd_drill(Namespace(reset=False))
    assert marker.exists(), "an existing drill was overwritten"
    assert "already exists" in capsys.readouterr().out

    cli.cmd_drill(Namespace(reset=True))
    assert not marker.exists(), "--reset did not start over"


def test_drill_is_never_the_default_issue(fake_issues):
    """`_`-prefixed directories are fixtures. A bare `sq build` must not
    wander into a practice run."""
    cli.cmd_drill(Namespace(reset=False))
    (fake_issues / "2026-fall").mkdir()
    shutil.copy(fake_issues / "_sample" / "issue.yaml",
                fake_issues / "2026-fall" / "issue.yaml")
    assert cli.resolve_issue(None).name == "2026-fall"


def test_drill_output_is_gitignored():
    """A drill means pasting real reprinted articles. They must not reach
    the repo — this one is a privacy rule, not tidiness."""
    ignore = (REPO / ".gitignore").read_text()
    assert "issues/_drill/" in ignore


# --- sq add --stdout -------------------------------------------------------

def test_add_stdout_writes_nothing_and_registers_nothing(tmp_path, capsys,
                                                          monkeypatch):
    """A paste is not always a NEW article — sometimes it is a fuller
    copy of one that already exists, whose file has hand-written
    frontmatter and real image paths in it. --stdout exists so that
    paste can be read and spliced instead of trampling the original."""
    from argparse import Namespace

    issues = tmp_path / "issues"
    shutil.copytree(REPO / "issues" / "_sample", issues / "_sample")
    monkeypatch.setattr(cli, "ISSUES", issues)
    before = (issues / "_sample" / "issue.yaml").read_text()
    n_before = len(list((issues / "_sample" / "articles").glob("*.md")))

    rc = cli.cmd_add(Namespace(
        issue="_sample", url="https://www.espn.com/x",
        paste=str(REPO / "tests/fixtures/espn.txt"), stdout=True,
        title="A Title", dek="", author="A Person", date="2026-01-01",
        publication=""))

    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("---")
    assert "bio: # TODO" in out
    assert (issues / "_sample" / "issue.yaml").read_text() == before
    assert len(list((issues / "_sample" / "articles").glob("*.md"))) == n_before
