"""Preflight checks — mostly the cover maths, which is the one that has
already caught a real problem and the one that is easy to get subtly
wrong."""

import pytest
from PIL import Image

from sq.preflight import cover_advice, cover_ppi, image_ppi, placed_width

# the verified Mixam media box
PAGE_W, PAGE_H = 499.68, 755.28


def plate(tmp_path, w, h, name="x.jpg"):
    p = tmp_path / name
    Image.new("RGB", (w, h), "grey").save(p)
    return p


# --- resolution ------------------------------------------------------------

def test_ppi_at_placed_size_not_raw_pixels(tmp_path):
    """The whole point: an image is only as sharp as the size it prints
    at. 1600 px across a 384pt column is 300 ppi; the same file floated
    at 44% of that column is comfortably over."""
    img = plate(tmp_path, 1600, 1000)
    assert image_ppi(img, 384.0) == pytest.approx(300, abs=1)
    assert image_ppi(img, 384.0 * 0.44) == pytest.approx(682, abs=1)


def test_cover_ppi_uses_the_binding_axis(tmp_path):
    """Fall 2026's actual cover: landscape, and the height is what limits
    it. Measuring by width would have reported 207 ppi and passed."""
    r, crop = cover_ppi(plate(tmp_path, 1440, 960), PAGE_W, PAGE_H)
    assert round(r) == 92
    assert round(crop * 100) == 56
    assert round(1440 / (PAGE_W / 72)) == 207      # what width alone claims


def test_cover_ppi_perfect_fit_has_no_crop(tmp_path):
    r, crop = cover_ppi(plate(tmp_path, 2082, 3147), PAGE_W, PAGE_H)
    assert r == pytest.approx(300, abs=1)
    assert crop == pytest.approx(0, abs=0.001)


# --- the advice ------------------------------------------------------------

def test_advice_names_the_binding_axis_and_the_shortfall(tmp_path):
    lines = " ".join(cover_advice(plate(tmp_path, 1440, 960), PAGE_W, PAGE_H))
    assert "landscape" in lines
    assert "height is what sets the resolution" in lines
    assert "3.28x short" in lines
    assert "2082 x 3147" in lines


def test_advice_does_not_call_a_portrait_image_landscape(tmp_path):
    """0.80 is portrait — just not as tall as a 0.66 page wants. Calling
    it landscape sends the reader looking for the wrong thing."""
    lines = " ".join(cover_advice(plate(tmp_path, 1330, 1663), PAGE_W, PAGE_H))
    assert "portrait at 0.80" in lines
    assert "landscape" not in lines
    assert "relatively wide" in lines


def test_advice_for_an_image_that_is_too_tall(tmp_path):
    lines = " ".join(cover_advice(plate(tmp_path, 1000, 3000), PAGE_W, PAGE_H))
    assert "relatively tall" in lines
    assert "top and bottom are cropped" in lines


def test_no_advice_when_the_art_is_right(tmp_path):
    assert cover_advice(plate(tmp_path, 2082, 3147), PAGE_W, PAGE_H) == []


def test_advice_never_suggests_upscaling(tmp_path):
    """Resolution cannot be manufactured. The fix is always a better
    source file, and the report must not imply otherwise."""
    for size in ((1440, 960), (1330, 1663), (1000, 3000)):
        lines = " ".join(cover_advice(plate(tmp_path, *size), PAGE_W, PAGE_H))
        for word in ("upscal", "enlarge", "resample", "interpolat"):
            assert word not in lines.lower()


# --- figure placement ------------------------------------------------------

@pytest.mark.parametrize("float_cls,expected", [
    ("", 383.68),                       # full column
    ("left", 383.68 * 0.44),            # floated figure
    ("right", 383.68 * 0.44),           # ditto, other side
    ("full", 499.68),                   # bleeds off the page
])
def test_placed_width_follows_the_stylesheet(float_cls, expected):
    g = {"column_w": 383.68, "media_w": 499.68}
    assert placed_width({"float": float_cls}, g) == pytest.approx(expected)


# --- accepting art that cannot be improved ---------------------------------

def make_issue(tmp_path, accept, back=(2082, 3147)):
    """Minimal issue dict shaped the way check_images() reads it. The back
    cover defaults to good art so the front is the only variable."""
    from PIL import Image
    (tmp_path / "images").mkdir(exist_ok=True)
    Image.new("RGBA", (1200, 600)).save(tmp_path / "images" / "mark.png")
    Image.new("RGB", (1440, 960)).save(tmp_path / "images" / "front.jpg")
    Image.new("RGB", back).save(tmp_path / "images" / "back.jpg")
    cover = {"image": "images/front.jpg"}
    if accept is not None:
        cover["accept_low_resolution"] = accept
    return {
        "dir": tmp_path,
        "mark": {"image": "images/mark.png"},
        "cover": cover,
        "back_cover": {"image": "images/back.jpg"},
        "articles": [],
        "geometry": {"media_w": PAGE_W, "media_h": PAGE_H,
                     "column_w": 383.68},
    }


def levels(capsys):
    return [l.split("]")[0].strip("  [")
            for l in capsys.readouterr().out.splitlines() if "] " in l]


def test_low_res_cover_fails_by_default(tmp_path, capsys):
    from sq.preflight import Report, check_images
    rep = Report()
    check_images(make_issue(tmp_path, None), rep)
    assert rep.fails >= 1, "a 92 ppi cover must fail unless accepted"


def test_accepting_low_resolution_downgrades_it_to_a_warning(tmp_path, capsys):
    """Covers are always full bleed, so when no better art exists the
    resolution is what gives. The decision is recorded in issue.yaml
    rather than left as a standing FAIL, because a check that can never
    pass is a check that stops being read."""
    from sq.preflight import Report, check_images
    rep = Report()
    check_images(make_issue(tmp_path, True), rep)
    assert rep.fails == 0
    assert rep.warns >= 1
    assert "accepted in issue.yaml" in capsys.readouterr().out


def test_accepting_does_not_excuse_the_back_cover(tmp_path, capsys):
    """The flag is per-image. Accepting the front must not quietly
    silence a back cover that is just as soft."""
    from sq.preflight import Report, check_images
    rep = Report()
    check_images(make_issue(tmp_path, True, back=(1440, 960)), rep)
    out = capsys.readouterr().out
    assert out.count("accepted in issue.yaml") == 1
    assert rep.fails == 1, "the back cover should still fail on its own"


# --- outgrowing the staples --------------------------------------------------

def test_warns_once_the_issue_is_too_thick_to_staple(tmp_path, capsys):
    """Mixam staples to roughly 60 pages and then switches the order to
    perfect binding on its own. That needs a printed spine, and the build
    makes two separate covers with none — so this has to be caught before
    the calculator does it silently."""
    from pathlib import Path

    from pypdf import PdfReader, PdfWriter

    from sq.content import load_issue
    from sq.preflight import SADDLE_STITCH_LIMIT, Report, check_pdf
    from sq.render import build as build_pdf

    sample = Path(__file__).resolve().parent.parent / "issues" / "_sample"
    thin = build_pdf(sample, tmp_path / "out")

    reader = PdfReader(str(thin))
    writer = PdfWriter()
    while len(writer.pages) <= SADDLE_STITCH_LIMIT + 3:
        for page in reader.pages:
            writer.add_page(page)
    thick = tmp_path / "thick.pdf"
    writer.write(str(thick))

    rep = Report()
    check_pdf(thick, load_issue(sample), rep)
    out = capsys.readouterr().out
    assert "perfect binding" in out
    assert "spine" in out
    assert rep.fails == 0, "too thick to staple is a warning, not a failure"
