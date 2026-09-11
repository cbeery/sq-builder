"""The `sq` command line.

    sq new 2027-spring
    sq add 2026-fall --paste article.txt --url https://...
    sq build 2026-fall [--watch]
    sq preflight 2026-fall
    sq proof 2026-fall

The issue slug is optional everywhere except `new`; it defaults to the
last issue directory in sorted order, which with YYYY-season naming is the
one being worked on.
"""

import argparse
import os
import sys
import time
from pathlib import Path
from string import Template

from . import __version__
from .content import ContentError, resolve_geometry

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "template"


def show(path: Path) -> str:
    """A readable path. The builder and the content are separate trees
    now, so nothing can be assumed to sit under ROOT — try the working
    directory first, then ROOT, then give the absolute path."""
    for base in (Path.cwd(), ROOT):
        try:
            return str(path.relative_to(base))
        except ValueError:
            continue
    return str(path)


def _content_root() -> Path:
    """Where the issues live.

    The builder and the words are separate repositories: the code is
    public, the reprinted articles and photographs are not. So content is
    found by looking outward — an explicit SQ_ISSUES, else an issues/
    directory beside wherever the command was run, else the builder's own,
    which is how the bundled sample is reached.
    """
    env = os.environ.get("SQ_ISSUES")
    if env:
        return Path(env).expanduser().resolve()
    here = Path.cwd() / "issues"
    if here.is_dir():
        return here
    return ROOT / "issues"


ISSUES = _content_root()
OUT = (ISSUES.parent / "out") if ISSUES != ROOT / "issues" else ROOT / "out"


def resolve_issue(slug: str | None) -> Path:
    if slug:
        path = ISSUES / slug if not Path(slug).is_dir() else Path(slug)
        if not (path / "issue.yaml").exists():
            raise ContentError(f"no issue.yaml in {path}")
        return path
    # `_`-prefixed directories are fixtures, not issues — issues/_sample is
    # the worked example of the dialect. Naming one explicitly still works.
    candidates = sorted(p for p in ISSUES.glob("*")
                        if (p / "issue.yaml").exists()
                        and not p.name.startswith("_"))
    if not candidates:
        raise ContentError(
            f"no issues found in {ISSUES}. Start one with `sq new <slug>`.")
    return candidates[-1]


def watched_files(issue_dir: Path):
    for pattern in ("issue.yaml", "articles/*.md", "images/*"):
        yield from issue_dir.glob(pattern)
    yield from TEMPLATE_DIR.glob("*.css")
    yield from TEMPLATE_DIR.glob("*.css.in")


def fingerprint(issue_dir: Path):
    return {p: p.stat().st_mtime for p in watched_files(issue_dir)
            if p.is_file()}


# --- commands --------------------------------------------------------------

def cmd_new(args) -> int:
    path = ISSUES / args.slug
    if path.exists():
        raise ContentError(f"{path} already exists")
    for sub in ("articles", "images"):
        (path / sub).mkdir(parents=True)

    g = resolve_geometry({})
    name = args.name or args.slug.replace("-", " ").title()
    text = Template((TEMPLATE_DIR / "issue.yaml.in").read_text()).substitute(
        issue_name=name,
        ideal_px=f"{g['media_w'] / 72 * 300:.0f} x {g['media_h'] / 72 * 300:.0f}",
        ideal_in=f"{g['media_w'] / 72:.2f} x {g['media_h'] / 72:.2f}",
        trim_w=f"{g['trim_w']:g}", trim_h=f"{g['trim_h']:g}",
        bleed=f"{g['bleed']:g}", quiet=f"{g['quiet']:g}",
        margin_top=f"{g['margin_top']:g}",
        margin_bottom=f"{g['margin_bottom']:g}",
        margin_inside=f"{g['margin_inside']:g}",
        margin_outside=f"{g['margin_outside']:g}")
    (path / "issue.yaml").write_text(text, encoding="utf-8")

    print(f"created {show(path)}")
    print("\nnext:")
    print(f"  1. drop the wordmark PNG into {path.name}/images/sq-mark.png")
    print(f"  2. drop cover art into {path.name}/images/")
    print(f"  3. sq add {path.name} --paste article.txt --url https://...")
    return 0


def cmd_add(args) -> int:
    from . import ingest
    issue_dir = resolve_issue(args.issue)

    paste = None
    if args.paste:
        # bytes, not text: pbpaste does not reliably hand back UTF-8
        paste = ingest.read_paste(args.paste)
    overrides = {"title": args.title, "dek": args.dek,
                 "author": args.author, "date": args.date,
                 "publication": args.publication}
    try:
        if args.stdout:
            # Nothing written, nothing registered — for when the paste is
            # a fuller copy of an article that already exists and the
            # existing file has work in it worth keeping.
            text, _ = ingest.clean_to_markdown(args.url, paste, overrides)
            sys.stdout.write(text)
            return 0
        path = ingest.add_article(issue_dir, args.url, paste=paste,
                                  overrides=overrides)
    except ingest.PaywallSuspected as exc:
        print(f"\n  {exc}\n", file=sys.stderr)
        return 1

    print(f"wrote {show(path)}")
    print(f"added to {show((issue_dir / 'issue.yaml'))}")
    print("\nnow, by hand:")
    print("  - write the bio (never scraped, never inferred)")
    print("  - check any <!-- REVIEW --> comments")
    print("  - drop real images in and fix the images/TODO-NN.jpg paths")
    return 0


def _build(issue_dir: Path, proof: bool, screen: bool = False) -> Path:
    from . import render
    t0 = time.time()
    pdf = render.build(issue_dir, OUT, proof=proof, screen=screen)
    from pypdf import PdfReader
    n = len(PdfReader(str(pdf)).pages)
    print(f"{show(pdf)}  —  {n} pages  {time.time() - t0:.2f}s")
    return pdf


def cmd_build(args) -> int:
    from . import preflight
    issue_dir = resolve_issue(args.issue)

    if getattr(args, "screen", False):
        pdf = _build(issue_dir, proof=False, screen=True)
        print("\nSymmetric margins and a folio that stays put — for reading "
              "on a screen.\nDo NOT send this one to the printer; it has no "
              "gutter.")
        return 0

    if not args.watch:
        pdf = _build(issue_dir, proof=False)
        print()
        clean = preflight.run(issue_dir, pdf)
        if not clean:
            print("\nThe PDF was written anyway — preflight is advisory here.")
            print("`sq preflight` is the gate, and it exits non-zero.")
        return 0

    print(f"watching {show(issue_dir)} — ctrl-c to stop")
    last = None
    while True:
        now = fingerprint(issue_dir)
        if now != last:
            last = now
            try:
                _build(issue_dir, proof=False)
            except ContentError as exc:
                print(f"  error: {exc}")
            except Exception as exc:                # keep the loop alive
                print(f"  error: {type(exc).__name__}: {exc}")
        time.sleep(0.5)


def cmd_preflight(args) -> int:
    from . import preflight
    issue_dir = resolve_issue(args.issue)
    pdf = None
    if args.pdf:
        pdf = Path(args.pdf)
    else:
        # Newest non-proof PDF for this issue. A proof carries crop marks
        # and must never be what gets checked, or uploaded.
        cands = sorted((p for p in OUT.glob("*.pdf")
                        if "_proof" not in p.name
                        and "_screen" not in p.name),
                       key=lambda p: p.stat().st_mtime)
        pdf = cands[-1] if cands else None
    return 0 if preflight.run(issue_dir, pdf) else 1


def cmd_proof(args) -> int:
    issue_dir = resolve_issue(args.issue)
    pdf = _build(issue_dir, proof=True)
    print("\nCrop marks are on. This file is for reading on screen.")
    print("Do NOT upload it to Mixam — upload the one from `sq build`.")
    return 0


# --- rehearsal -------------------------------------------------------------

DRILL = "_drill"

# Every role the stylesheet declares. --ui-face is unused at present but
# still probed: if furniture ever wants its own voice back, it should be
# a one-line change and not a discovery that the font went missing.
FONT_ROLES = [
    ("Headline", "--display-face", 900),
    ("Subhead", "--display-alt", 700),
    ("Body", "--body-face", 400),
    ("Furniture", "--cond-face", 400),
    ("Unused", "--ui-face", 400),
]


def cmd_drill(args) -> int:
    """Scaffold a throwaway issue for a practice run.

    Four issues a year is not enough to stay fluent, so this exists to be
    used between them: grab a few articles, run the whole pipeline, look
    at the PDF, throw it away. It borrows the sample's placeholder
    artwork so it builds the moment it is created, and it is gitignored —
    a drill involves pasting real reprinted articles, and those must not
    reach the repo.
    """
    import shutil

    path = ISSUES / DRILL
    if path.exists():
        if not args.reset:
            print(f"{show(path)} already exists.")
            print("Carry on adding to it, or start over with "
                  "`sq drill --reset`.")
            return 0
        shutil.rmtree(path)

    sample = ISSUES / "_sample"
    (path / "articles").mkdir(parents=True)
    shutil.copytree(sample / "images", path / "images")
    text = (sample / "issue.yaml").read_text(encoding="utf-8")
    text = text.split("title:", 1)[1]
    text = ("# A throwaway issue for a practice run. Gitignored — a drill\n"
            "# means pasting real reprinted articles, and those must not\n"
            "# reach the repo. Reset it with `sq drill --reset`.\n"
            "title:" + text)
    text = text.replace("issue: Sample", "issue: Drill")
    text = text.replace("subtitle: A worked example of the dialect",
                        "subtitle: A practice run")
    text = text.replace("  - articles/01-dialect.md\n", "")
    (path / "issue.yaml").write_text(text, encoding="utf-8")

    print(f"created {show(path)} (gitignored)\n")
    print("Now, for each article you want to practise with:")
    print(f"  pbpaste | sq add {DRILL} --paste - --url https://...\n")
    print("Then:")
    print(f"  sq build {DRILL}      # renders and preflights")
    print(f"  open out/SQ_Drill_*.pdf\n")
    print("Real cover art is optional — placeholder art is already in "
          "place so it builds straight away.")
    print(f"Start over any time with `sq drill --reset`.")
    return 0


def probe_font(role: str, var: str, weight: int) -> set:
    """Render one line in a role's face and report what actually got
    embedded. Substitution is silent — the engine swaps without warning
    and the PDF looks plausible until it prints — so the only honest
    check is to look at the finished file."""
    import io

    from pypdf import PdfReader
    from weasyprint import CSS, HTML

    from .preflight import embedded_fonts
    from .render import STYLESHEET

    probe = (f'<p style="font-family: var({var}); font-weight: {weight}">'
             f'Hamburgefonstiv 0123</p>')
    # sq.css puts the folio in an @page margin box, which would embed the
    # furniture face into every probe and make each role look like a hit.
    quiet = ("@page { size: 200pt 60pt; margin: 8pt;"
             "  @bottom-right { content: none } @bottom-left { content: none } }")
    buf = io.BytesIO()
    HTML(string=f"<body>{probe}</body>").write_pdf(
        buf, stylesheets=[CSS(filename=str(STYLESHEET)), CSS(string=quiet)])
    buf.seek(0)
    return set(embedded_fonts(PdfReader(buf)))


def font_matches(wanted: str, got: str) -> bool:
    """Did we get the family we asked for, or a fallback?

    Compares the family stem rather than the whole name. Pango describes
    a face by weight and width class, not by its full name, so
    `Mazzard H Black` legitimately comes back as
    `Mazzard-Heavy-Semi-Condensed` — the OTF has family "Mazzard",
    weight 900, width class 4. Insisting on an exact match reports a
    false failure on a font that is installed and correct.

    What actually needs catching is the family going missing on a fresh
    machine and the engine silently reaching for a fallback.
    """
    return _norm(wanted.split()[0]) in _norm(got)


def cmd_doctor(args) -> int:
    """Is the toolchain sound? Mostly: do the five faces actually
    resolve, or is the engine quietly substituting?"""
    ok = True
    renamed = False
    print("Fonts — what each role actually embeds\n")
    for role, var, weight in FONT_ROLES:
        got = probe_font(role, var, weight)
        name = ", ".join(sorted(got)) or "NOTHING EMBEDDED"
        wanted = _first_family(var)          # wanted face, before fallbacks
        hit = any(font_matches(wanted, g) for g in got)
        exact = any(_norm(wanted) in _norm(g) for g in got)
        if not hit:
            ok = False
        if hit and not exact:
            renamed = True
        print(f"  [{'OK' if hit else 'FAIL'}] {role:<10} want "
              f"{wanted:<24} got {name}")
    if renamed:
        print()
        print("  A name that does not match exactly is fine. The engine "
              "describes a face by")
        print("  weight and width class, so \"Mazzard H Black\" embeds as "
              "\"Mazzard-Heavy-")
        print("  Semi-Condensed\". What matters is the family, and that it "
              "is not a fallback.")

    print("\nSample issue")
    from . import preflight
    from . import render
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        try:
            pdf = render.build(ISSUES / "_sample", Path(tmp))
            clean = preflight.run(ISSUES / "_sample", pdf)
        except Exception as exc:
            print(f"  [FAIL] sample issue did not build: {exc}")
            clean = False
    ok = ok and clean

    print(f"\n{'ALL GOOD' if ok else 'PROBLEMS FOUND'}")
    return 0 if ok else 1


def _norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def _first_family(var: str) -> str:
    """The first family named in a custom property in sq.css — the one
    that is actually wanted, before the fallbacks."""
    import re

    from .render import STYLESHEET
    css = STYLESHEET.read_text(encoding="utf-8")
    m = re.search(rf"{re.escape(var)}\s*:\s*([^;]+);", css)
    if not m:
        return "?"
    return m.group(1).split(",")[0].strip().strip('"').strip()


# --- entry point -----------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="sq", description="Stan Quarterly — Markdown in, print PDF out.")
    ap.add_argument("--version", action="version",
                    version=f"sq {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new", help="scaffold a new issue")
    p.add_argument("slug", help="directory name, e.g. 2027-spring")
    p.add_argument("--name", default="", help='issue name, e.g. "Spring 2027"')
    p.set_defaults(fn=cmd_new)

    p = sub.add_parser("add", help="ingest an article (paste-first)")
    p.add_argument("issue", nargs="?")
    p.add_argument("--url", required=True,
                   help="source URL; used for metadata even when paywalled")
    p.add_argument("--paste", help="text file of the browser copy, or - for stdin")
    p.add_argument("--stdout", action="store_true",
                   help="print the cleaned Markdown instead of writing a "
                        "file; leaves issue.yaml alone")
    for f in ("title", "dek", "author", "date", "publication"):
        p.add_argument(f"--{f}", default="",
                       help=f"override the {f} from page metadata")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("build", help="render the print PDF")
    p.add_argument("issue", nargs="?")
    p.add_argument("--watch", action="store_true", help="rebuild on save")
    p.add_argument("--screen", action="store_true",
                   help="symmetric margins for on-screen reading; not for "
                        "the printer")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("preflight", help="check an issue before upload")
    p.add_argument("issue", nargs="?")
    p.add_argument("--pdf", help="PDF to check (default: newest in out/)")
    p.set_defaults(fn=cmd_preflight)

    p = sub.add_parser("proof", help="render with crop marks, for screen")
    p.add_argument("issue", nargs="?")
    p.set_defaults(fn=cmd_proof)

    p = sub.add_parser("drill", help="scaffold a throwaway issue to practise on")
    p.add_argument("--reset", action="store_true",
                   help="delete the existing drill issue and start over")
    p.set_defaults(fn=cmd_drill)

    p = sub.add_parser("doctor", help="check the fonts and the toolchain")
    p.set_defaults(fn=cmd_doctor)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except ContentError as exc:
        print(f"\nerror: {exc}\n", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
