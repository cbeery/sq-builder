#!/usr/bin/env python3
"""Turn a browser copy/paste into SQ Markdown.

Paste-first by design. The usual SQ sources are paywalled or JS-rendered,
so the body text arrives as a manual copy out of the browser and only the
metadata comes off the wire. `sq add --url` alone is the opportunistic
path, not the normal one.

Deliberately conservative: when a rule isn't sure, it leaves a `# REVIEW`
comment in the output rather than guessing. Expect to hand-edit the result.
"""

import codecs
import pathlib
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

# ------------------------------------------------------------------ decode

def _mac_roman_fallback(exc):
    """Decode one stray byte as Mac OS Roman and carry on."""
    return (exc.object[exc.start:exc.end].decode("mac_roman"), exc.end)


codecs.register_error("sq_mac_roman", _mac_roman_fallback)


def decode_paste(raw: bytes) -> str:
    """Bytes off the clipboard -> text, whatever pbpaste felt like emitting.

    macOS `pbpaste` does not always hand back UTF-8: a copy out of Safari
    or TextEdit can arrive as Mac OS Roman, where 0xB0 is an apostrophe
    and 0x8E is an e-acute. Reading that as UTF-8 either raises or, worse,
    silently mangles a character that then prints wrong.

    Valid UTF-8 is decoded as UTF-8; only the bytes that cannot be are
    reinterpreted, so a genuinely mixed paste survives intact either way.
    """
    return raw.decode("utf-8", "sq_mac_roman")


def read_paste(path) -> str:
    """Read a paste from a file, or from stdin when path is '-'."""
    import sys
    if str(path) == "-":
        return decode_paste(sys.stdin.buffer.read())
    return decode_paste(pathlib.Path(path).read_bytes())


# ---------------------------------------------------------------- normalise

INVISIBLES = dict.fromkeys(map(ord, "\u00ad\u200b\u200c\u200d\u2060\ufeff"), None)


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.translate(INVISIBLES)
    text = text.replace("\u00a0", " ").replace("\u2009", " ").replace("\u202f", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def typographic(s: str) -> str:
    """ESPN pastes use -- for em dashes; WaPo already ships real ones."""
    s = re.sub(r"(?<=\w) -- (?=\w)", "\u2014", s)
    s = re.sub(r"(?<=\w)---(?=\w)", "\u2014", s)
    return s


# ------------------------------------------------------------------ profiles

GENERIC_JUNK = {
    "share", "save", "comment", "comments", "gift article", "listen",
    "more article actions", "chevron right", "summary", "next", "play",
    "advertisement", "skip to end of carousel", "end of carousel",
    "read more", "sign in", "subscribe", "follow", "log in",
}

GENERIC_JUNK_RE = [
    re.compile(r"^\d+$"),                       # reaction / comment counts
    re.compile(r"^[\d,]+$"),
    re.compile(r"^\d+\s*min(ute)?s?( read)?$", re.I),
    re.compile(r"^make us preferred on google$", re.I),
    re.compile(r"^open extended reactions$", re.I),
    re.compile(r"^like\s*like$", re.I),
    re.compile(r"^likelaughfire$", re.I),
    re.compile(r"^\w[\w\s']{0,60}\(\d+:\d\d\)$"),   # video player: "... (0:35)"
]

# Mid-article recirculation modules: strip from the marker until prose resumes.
RECIRC_START = re.compile(
    r"^(editor'?s picks|popular articles|most read|more from|related|"
    r"trending now|you may also like)$", re.I)

CREDIT_WORDS = re.compile(
    r"(Getty Images|Getty|AP\b|Reuters|USA Today|Imagn|Sportswire|"
    r"Bettmann|Archive|for ESPN|Icon Sportswire|Clarion-Ledger|"
    r"Courtesy of|/[A-Z][a-z]+ [A-Z][a-z]+$)")

PROFILES = {
    "espn.com": {
        "caption": "trailing-credit",
        "smallcaps_leadin": True,
        "publication": "ESPN",
    },
    "boulderreportinglab.org": {
        "caption": "trailing-credit",
        "smallcaps_leadin": False,
        "publication": "Boulder Reporting Lab",
    },
    "washingtonpost.com": {
        "caption": "paren-credit",
        "smallcaps_leadin": False,
        "publication": "The Washington Post",
    },
}


def profile_for(url: str) -> dict:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    for key, prof in PROFILES.items():
        if host.endswith(key):
            return prof
    return {"caption": "both", "smallcaps_leadin": False, "publication": ""}


# ------------------------------------------------------------------- helpers

def is_prose(line: str) -> bool:
    """Long and terminally punctuated — good enough to mark the end of a
    recirculation block, where headlines are short or unpunctuated."""
    return len(line) > 100 and line.rstrip().endswith((".", '."', ".\u201d", "!", "?\u201d"))


def is_junk(line: str) -> bool:
    low = line.strip().lower()
    if low in GENERIC_JUNK:
        return True
    return any(rx.match(line.strip()) for rx in GENERIC_JUNK_RE)


PAREN_CREDIT = re.compile(r"^(?P<cap>.+?)\s*\((?P<credit>[^()]{2,60})\)\s*$")


def as_caption(line: str, mode: str):
    """Is this paragraph really a photo caption?

    Returns (caption, credit, confidence) or None. The credit is pulled
    out as its own string rather than left on the end of the caption —
    it is metadata about the image and gets set differently. It may come
    back empty when a caption is detected but no credit is identifiable.
    """
    if mode == "both":
        return (as_caption(line, "paren-credit")
                or as_caption(line, "trailing-credit"))
    if mode == "paren-credit":
        # WaPo style: "...handle the manual transmissions. (Courtesy of X)"
        m = PAREN_CREDIT.match(line)
        if m and not m.group("credit").endswith("."):
            return m.group("cap").strip(), m.group("credit").strip(), "credit"
        return None

    # trailing-credit (ESPN): the line ends with a bare credit, not a sentence
    s = line.strip()
    parts = re.split(
        r"(?:(?<=[.!?][\"\u201d\u2019\'])|(?<=[.!?]))\s+", s)
    tail = parts[-1]
    if len(parts) >= 2 and CREDIT_WORDS.search(tail) and len(tail) < 80:
        return " ".join(parts[:-1]).strip(), tail.strip(), "credit"
    if CREDIT_WORDS.search(s) and len(s) < 120 and not s.endswith("."):
        # the whole line is the credit; there is no caption to keep
        return "", s, "credit"
    # weaker: unpunctuated line ending in a short Title Case phrase
    if not s.endswith((".", "!", "?", "\u201d", '"')) and len(parts) >= 2:
        words = tail.split()
        if 1 < len(words) <= 6 and all(w[:1].isupper() for w in words if w[:1].isalpha()):
            return " ".join(parts[:-1]).strip(), tail.strip(), "weak"
    return None


# ESPN opens each section with a small-caps run. The first word must be
# alphabetic; later ones may carry digits or internal periods, because the
# runs contain years ("BACK IN 1964,") and initialisms, and the run may end
# on a full stop ("MARCUS HALLOWAY IS 20."). Three words minimum — every real
# run is at least that, and it stops an ordinary opener like "A TV station
# called..." being swept up.
LEADIN = re.compile(
    r"^([A-Z][A-Z'\u2019\-.]*[,:;.]?"
    r"(?:\s+[A-Z0-9][A-Z0-9'\u2019\-.]*[,:;.]?){2,5})"
    r"\s+(?=[a-z]|[A-Z][a-z])")


def mark_leadin(line: str):
    """ESPN starts each section with a small-caps run: 'BY THE TIME Konnor...'"""
    m = LEADIN.match(line)
    if not m:
        return None
    run = m.group(1)
    return "{sc}" + run + "{/sc}" + line[m.end(1):]


# ---------------------------------------------------------------------- main

# A byline is a short line naming a person - never a sentence that opens
# with "By 1933, ...". Require capitalised name words and a length cap.
BYLINE = re.compile(
    r"^[Bb]y\s+[A-Z][A-Za-z.\u2019'\-]+(?:\s+[A-Z][A-Za-z.\u2019'\-]+){0,3}$")
DATEISH = re.compile(
    r"^([A-Z][a-z]{2}\s+\d{1,2},?\s+\d{4}.*|"
    r"[A-Z][a-z]+\s+\d{1,2},\s+\d{4})$")


def is_byline(line: str) -> bool:
    return len(line) < 60 and bool(BYLINE.match(line))

BODY_MIN = 150


def clean(text: str, prof: dict, meta: dict = None) -> list:
    meta = meta or {}
    text = normalise(text)
    paras = [p.strip() for p in text.split("\n") if p.strip()]

    # --- header zone -----------------------------------------------------
    known = {v.strip() for v in (meta.get("title"), meta.get("dek"),
                                 meta.get("author")) if v}
    # --- header zone: one linear pass, no lookahead ---------------------
    # Chrome above the article. A long line seen BEFORE any byline/date is
    # the dek; the first long line AFTER one is where the body starts.
    header, body_start, dek_guess, seen_byline = [], len(paras), None, False
    for idx, p in enumerate(paras):
        if p in known:
            continue
        if len(p) < 60 and (DATEISH.match(p) or is_byline(p)):
            seen_byline = True
            continue
        if is_junk(p):
            continue
        if as_caption(p, prof["caption"]):
            header.append(p)
            continue
        if len(p) >= BODY_MIN:
            if not seen_byline and dek_guess is None and idx < 6 \
                    and not meta.get("dek"):
                dek_guess = p
                continue
            body_start = idx
            break

    if dek_guess:
        meta["dek"] = dek_guess
        meta["_dek_guessed"] = True

    paras = header + paras[body_start:]

    out, img_n, i = [], 0, 0
    while i < len(paras):
        p = paras[i]

        if is_junk(p):
            i += 1
            continue

        if RECIRC_START.match(p):
            i += 1
            skipped = 0
            while i < len(paras) and not is_prose(paras[i]):
                i += 1
                skipped += 1
            out.append(("comment", f"REVIEW: dropped {skipped} lines of "
                                   f"recirculation module after '{p}'"))
            continue

        if p in known or (len(p) < 60 and (DATEISH.match(p) or is_byline(p))):
            i += 1
            continue

        hit = as_caption(p, prof["caption"])
        if hit:
            cap, credit, confidence = hit
            img_n += 1
            if confidence == "weak":
                out.append(("comment", "REVIEW: caption or body text?"))
            out.append(("figure", cap, f"images/TODO-{img_n:02d}.jpg", credit))
            i += 1
            continue

        if prof["smallcaps_leadin"]:
            marked = mark_leadin(p)
            if marked:
                out.append(("dropcap", typographic(marked)))
                i += 1
                continue

        out.append(("para", typographic(p)))
        i += 1

    return out


def to_markdown(blocks, meta) -> str:
    lines = ["---"]
    for k in ("title", "dek", "author", "publication", "date", "url"):
        v = meta.get(k) or "# TODO"
        lines.append(f"{k}: {v}" if v == "# TODO" else f'{k}: "{v}"')
    lines += ["bio: # TODO", "---", ""]
    if meta.get("_dek_guessed"):
        lines += ["<!-- REVIEW: dek was guessed from the paste, not supplied -->", ""]

    first_para_seen = False
    for b in blocks:
        if b[0] == "comment":
            lines += [f"<!-- {b[1]} -->", ""]
        elif b[0] == "figure":
            cap, src, credit = b[1], b[2], (b[3] if len(b) > 3 else "")
            alt = f"{cap} | {credit}" if credit else cap
            lines += [f"![{alt}]({src})", ""]
        elif b[0] == "dropcap":
            first_para_seen = True
            lines += [f"@@ {b[1]}", ""]
        else:
            if not first_para_seen:
                first_para_seen = True
                lines += [f"@@ {b[1]}", ""]
            else:
                lines += [b[1], ""]
    return "\n".join(lines)


# ------------------------------------------------------- metadata from URL

META_KEYS = {
    "title": ("og:title", "twitter:title"),
    "author": ("article:author", "author", "byl"),
    "date": ("article:published_time", "datePublished", "date"),
    "publication": ("og:site_name",),
    "dek": ("og:description", "description"),
}

META_RE = re.compile(
    r"<meta[^>]+?(?:property|name|itemprop)\s*=\s*[\"']([^\"']+)[\"'][^>]*?"
    r"content\s*=\s*[\"']([^\"']*)[\"']", re.I)
META_RE_REV = re.compile(
    r"<meta[^>]+?content\s*=\s*[\"']([^\"']*)[\"'][^>]*?"
    r"(?:property|name|itemprop)\s*=\s*[\"']([^\"']+)[\"']", re.I)


FETCH_TIMEOUT = 8          # seconds
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def fetch_html(url: str, timeout: int = FETCH_TIMEOUT):
    """Fetch a page, or give up quickly.

    The normal path is paste-first: the body already came out of the
    browser and this is only after metadata. A slow or unreachable URL
    must not stall the command, so this has a short timeout and swallows
    every failure — the caller falls back to `# TODO` frontmatter.
    """
    import urllib.error
    import urllib.request
    try:
        # Request() itself raises on a malformed URL, so it belongs
        # inside the guard: a typo must not crash `sq add`.
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode(r.headers.get_content_charset() or "utf-8",
                                   errors="replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def fetch_metadata(url: str) -> dict:
    """Page metadata is usually served to unauthenticated requests even when
    the body is paywalled, so this is worth trying for every source. Returns
    only what it actually found — never guesses."""
    html = fetch_html(url)
    if not html:
        return {}
    tags = {}
    for k, v in META_RE.findall(html):
        tags.setdefault(k.lower(), v.strip())
    for v, k in META_RE_REV.findall(html):
        tags.setdefault(k.lower(), v.strip())

    meta = {}
    for field, keys in META_KEYS.items():
        for key in keys:
            if tags.get(key.lower()):
                meta[field] = unescape_entities(tags[key.lower()])
                break
    if meta.get("date"):
        meta["date"] = meta["date"][:10]        # ISO timestamp -> date
    if not meta.get("author"):
        m = re.search(r'"author"\s*:\s*{[^}]*?"name"\s*:\s*"([^"]{2,60})"',
                      html)
        if m:
            meta["author"] = unescape_entities(m.group(1))
    return meta


def unescape_entities(s: str) -> str:
    import html as _html
    return _html.unescape(s).strip()


MIN_EXTRACTED_WORDS = 400


class PaywallSuspected(Exception):
    """Extraction returned too little to be a real article."""


def extract_url(url: str) -> str:
    """Opportunistic body extraction for the occasional source that isn't
    paywalled. Refuses to return a stub that would look complete but isn't."""
    import trafilatura
    html = fetch_html(url)
    if not html:
        raise PaywallSuspected(
            f"could not fetch {url} within {FETCH_TIMEOUT}s")
    text = trafilatura.extract(html, include_comments=False,
                               include_tables=False) or ""
    words = len(text.split())
    if words < MIN_EXTRACTED_WORDS:
        raise PaywallSuspected(
            f"extracted only {words} words from {url}. That source is almost "
            f"certainly paywalled or JS-rendered.\n"
            f"Copy the article out of the browser and use:\n"
            f"    sq add <issue> --paste article.txt --url {url}")
    return text


# ------------------------------------------------------------- file writing

def slugify(title: str, fallback: str = "article") -> str:
    s = unicodedata.normalize("NFKD", title or "")
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    # Short and recognisable beats complete; the number carries the ordering.
    return "-".join(s.split("-")[:4]) or fallback


def next_index(articles_dir: Path) -> int:
    existing = [int(m.group(1))
                for p in articles_dir.glob("*.md")
                if (m := re.match(r"(\d+)-", p.name))]
    return max(existing, default=0) + 1


def append_to_issue(issue_yaml: Path, rel: str) -> None:
    """Append textually rather than round-tripping the YAML, so the comments
    in issue.yaml survive."""
    lines = issue_yaml.read_text(encoding="utf-8").splitlines()
    entry = f"  - {rel}"
    if any(l.strip() == entry.strip() for l in lines):
        return
    last = max((i for i, l in enumerate(lines)
                if re.match(r"\s*-\s*articles/", l)), default=None)
    if last is None:
        last = max((i for i, l in enumerate(lines)
                    if re.match(r"articles\s*:", l)), default=len(lines) - 1)
    lines.insert(last + 1, entry)
    issue_yaml.write_text("\n".join(lines) + "\n", encoding="utf-8")


def clean_to_markdown(url: str, paste: str | None = None,
                      overrides: dict | None = None) -> tuple:
    """Metadata + cleaned body -> SQ Markdown, without writing anything.

    Separate from add_article() because a paste is not always a new
    article: sometimes it is a fuller copy of one that already exists,
    and the existing file has hand-written frontmatter and real image
    paths that must not be trampled. `sq add --stdout` uses this so the
    result can be read, diffed and spliced by hand.
    """
    meta = fetch_metadata(url)
    prof = profile_for(url)
    meta.setdefault("publication", prof.get("publication", ""))
    meta.update({k: v for k, v in (overrides or {}).items() if v})
    meta["url"] = url

    raw = paste if paste is not None else extract_url(url)
    return to_markdown(clean(raw, prof, meta), meta) + "\n", meta


def add_article(issue_dir: Path, url: str, paste: str | None = None,
                overrides: dict | None = None) -> Path:
    """The whole ingestion path: metadata from the URL, body from the paste
    (or from extraction when the source allows it), cleaned into SQ Markdown
    and registered in issue.yaml.

    The result is always hand-edited afterwards. That is expected — the aim
    is 'obvious what still needs fixing', not 'looks finished'.
    """
    text, meta = clean_to_markdown(url, paste, overrides)

    articles = issue_dir / "articles"
    articles.mkdir(parents=True, exist_ok=True)
    n = next_index(articles)
    path = articles / f"{n:02d}-{slugify(meta.get('title', ''))}.md"
    path.write_text(text, encoding="utf-8")
    append_to_issue(issue_dir / "issue.yaml", f"articles/{path.name}")
    return path
