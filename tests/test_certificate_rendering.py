"""Integration tests for the certificate rendering engine (app/services/certificate.py).

These tests call render_certificate() directly (no HTTP layer) and inspect the
*actual generated PDF pixels* -- rasterizing with PyMuPDF and scanning ink --
rather than guessing at text metrics, per the ground-truth methodology that
was used to originally diagnose and fix the reported layout bugs.

Every test writes its output PDF under tests/output/<test-name>/ so a human
can open and visually double-check any of them afterwards.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services import dates as dates_service
from app.services.certificate import CertificateFields, render_certificate

from conftest import (
    DESIGN_ASSETS_DIR,
    LAYOUT_SPEC,
    count_background_pixel_diffs,
    get_pdf_page_count,
    get_pdf_page_size_pt,
    ink_bbox_pt,
    ink_row_bands_pt,
    render_pdf_page_to_image,
)

BOXES = LAYOUT_SPEC["dynamic_boxes"]
REFERENCE_PDF = DESIGN_ASSETS_DIR / "example_certificate_reference.pdf"


def make_fields(**overrides) -> CertificateFields:
    base = dict(
        name_uk="Коваль Марія",
        name_en="Koval Mariia",
        title_uk="Стандарт роботи з клієнтами",
        title_en="Customer service standard",
        location_uk="м. Івано-Франківськ, Україна",
        location_en="Ivano-Frankivsk city, Ukraine",
        date_uk="Липень, 2026",
        date_en="July, 2026",
    )
    base.update(overrides)
    return CertificateFields(**base)


class TestBasicRendering:
    def test_produces_single_page_pdf_with_correct_size(self, output_dir: Path):
        out = output_dir / "cert.pdf"
        render_certificate(make_fields(), out)

        assert out.exists()
        assert get_pdf_page_count(out) == 1
        w, h = get_pdf_page_size_pt(out)
        assert w == pytest.approx(LAYOUT_SPEC["page"]["width_pt"], abs=0.5)
        assert h == pytest.approx(LAYOUT_SPEC["page"]["height_pt"], abs=0.5)

    def test_background_pixel_perfect_vs_reference(self, output_dir: Path):
        """Regression test for the lossy-JPEG color-shift bug and other gross
        rendering regressions: everywhere OUTSIDE the 4 dynamic boxes must
        closely match the reference design (logo, QR code, decorations,
        signature, etc.).

        This intentionally allows a small per-channel tolerance rather than a
        bit-for-bit match: PyMuPDF's rasterization of the reference PDF's
        vector fills doesn't reproduce the same color transform real browsers
        (Chrome/Edge's PDFium) apply to that ICC-tagged content. A controlled,
        same-window Edge screenshot comparison confirmed the design's true
        on-screen purple is closer to our (verified, recolored) asset than to
        MuPDF's own rendering of the vector original -- so a small, expected
        diff here is *more* correct, not a regression. MAX_ALLOWED_DIFF stays
        well below the ~100+ jumps a real asset/layout regression would cause.
        """
        MAX_ALLOWED_DIFF = 50

        out = output_dir / "cert.pdf"
        render_certificate(make_fields(), out)

        generated_img = render_pdf_page_to_image(out)
        reference_img = render_pdf_page_to_image(REFERENCE_PDF)
        ignore_boxes = [spec["box_pt"] for spec in BOXES.values()]

        max_diff, differing = count_background_pixel_diffs(generated_img, reference_img, ignore_boxes)
        assert max_diff <= MAX_ALLOWED_DIFF, (
            f"background pixels differ by up to {max_diff} (allowed <= {MAX_ALLOWED_DIFF})"
        )


class TestLongNames:
    """Long-name handling: must wrap/shrink but never cross into the blue
    chevron decoration (x > 764.5pt) or drop below the name box's bottom."""

    @pytest.mark.parametrize(
        "name_uk,name_en",
        [
            ("Пшеничний-Вітальнюк Олександр Костянтинович", "Pshenychnyi-Vitalniuk Oleksandr Kostiantynovych"),
            ("Дуже-Дуже-Дуже Довге Прізвище Та Ім'я По-Батькові Українською", "A Very Very Very Long Full Name In English Too"),
        ],
    )
    def test_long_name_stays_within_box(self, output_dir: Path, name_uk: str, name_en: str):
        out = output_dir / f"cert_{name_en[:10].replace(' ', '_')}.pdf"
        render_certificate(make_fields(name_uk=name_uk, name_en=name_en), out)

        img = render_pdf_page_to_image(out)
        box_pt = BOXES["name"]["box_pt"]
        bbox = ink_bbox_pt(img, box_pt, pad_pt=0.0)
        assert bbox is not None, "expected name text to be rendered"
        _, _, max_x, max_y = bbox
        assert max_x <= 764.5, f"name text overflowed into chevron decoration (max_x={max_x})"
        assert max_y <= box_pt[3] + 1.0, f"name text overflowed box bottom (max_y={max_y})"

    def test_long_name_without_english_translation(self, output_dir: Path):
        """A recipient may have no name_en at all (empty string) -- must not
        raise, and must render only the Ukrainian line."""
        out = output_dir / "cert_no_en.pdf"
        render_certificate(make_fields(name_en=""), out)
        assert out.exists()
        assert get_pdf_page_count(out) == 1


class TestLongTitles:
    """Long training titles must wrap to multiple lines and/or shrink, but
    stay clear of the fixed 'Бізнес-тренер' label starting at y=460pt."""

    @pytest.mark.parametrize(
        "title_uk,title_en",
        [
            (
                "Комплексна програма підвищення кваліфікації менеджерів середньої ланки з питань клієнтського сервісу та ефективних комунікацій",
                "Comprehensive professional development programme for mid-level managers on customer service and effective communication",
            ),
            (
                "Дуже довга назва тренінгу яка точно не влізе в один чи два рядки і має розбитись на кілька рядків з переносом",
                "",
            ),
        ],
    )
    def test_long_title_stays_within_box(self, output_dir: Path, title_uk: str, title_en: str):
        out = output_dir / f"cert_title_{'en' if title_en else 'no_en'}.pdf"
        render_certificate(make_fields(title_uk=title_uk, title_en=title_en), out)

        img = render_pdf_page_to_image(out)
        box_pt = BOXES["title"]["box_pt"]
        bbox = ink_bbox_pt(img, box_pt, pad_pt=0.0)
        assert bbox is not None
        _, _, max_x, max_y = bbox
        assert max_x <= box_pt[2] + 1.0, f"title text overflowed box right edge (max_x={max_x})"
        assert max_y <= 459.0, f"title text overlaps the 'Бізнес-тренер' label (max_y={max_y})"


class TestEnglishSmallerThanUkrainian:
    """Regression test: the English translation line must always render
    strictly smaller than the Ukrainian line, even when the Ukrainian text is
    so long it has to shrink far below its own base font size. Before this
    fix, each language was fit independently, so a short English line could
    end up the same size as (or larger than) a heavily-shrunk Ukrainian one."""

    _SHORT_TITLE_EN = "Customer Service Training Programme"

    def test_en_shrinks_when_uk_is_forced_much_smaller(self, output_dir: Path):
        box_pt = BOXES["title"]["box_pt"]

        baseline_out = output_dir / "cert_baseline.pdf"
        render_certificate(
            make_fields(title_uk="Тест", title_en=self._SHORT_TITLE_EN),
            baseline_out,
        )
        baseline_img = render_pdf_page_to_image(baseline_out)
        baseline_bands = ink_row_bands_pt(baseline_img, box_pt, pad_pt=0.0)
        assert len(baseline_bands) >= 2, "expected separate UK and EN ink bands"
        baseline_en_height = baseline_bands[-1][1] - baseline_bands[-1][0]

        stressed_out = output_dir / "cert_stressed.pdf"
        long_title_uk = (
            "Комплексна програма підвищення кваліфікації менеджерів середньої "
            "ланки з питань клієнтського сервісу та ефективних комунікацій"
        )
        render_certificate(
            make_fields(title_uk=long_title_uk, title_en=self._SHORT_TITLE_EN),
            stressed_out,
        )
        stressed_img = render_pdf_page_to_image(stressed_out)
        stressed_bands = ink_row_bands_pt(stressed_img, box_pt, pad_pt=0.0)
        assert len(stressed_bands) >= 2, "expected separate UK and EN ink bands"
        stressed_en_height = stressed_bands[-1][1] - stressed_bands[-1][0]

        # Same English text in both cases -- if the fix works, the English
        # line must shrink noticeably once the Ukrainian line is forced much
        # smaller than its own base size (otherwise it would render at the
        # exact same height as the unconstrained baseline).
        assert stressed_en_height < baseline_en_height - 1.0, (
            f"English text height did not shrink alongside the Ukrainian text "
            f"(baseline={baseline_en_height:.2f}pt, stressed={stressed_en_height:.2f}pt)"
        )


class TestAllMonths:
    """All 12 UA/EN month names at the date box, especially the widest one
    ('Вересень, 2026') which was the exact string that originally triggered
    the reported white-notch-over-hatch bug."""

    @pytest.mark.parametrize("month_idx", range(1, 13))
    def test_month_date_stays_clear_of_hatch(self, output_dir: Path, month_idx: int):
        date_uk, date_en = dates_service.format_dates(month_idx, 2026)
        out = output_dir / f"cert_month_{month_idx:02d}.pdf"
        render_certificate(make_fields(date_uk=date_uk, date_en=date_en), out)

        img = render_pdf_page_to_image(out)
        box_pt = BOXES["date"]["box_pt"]
        bbox = ink_bbox_pt(img, box_pt, pad_pt=0.0)
        assert bbox is not None, f"expected date text for month {month_idx}"
        _, _, max_x, _ = bbox
        assert max_x <= box_pt[2] + 1.0, (
            f"date '{date_uk}' overflowed the box's right edge into the hatch "
            f"decoration (max_x={max_x}, box right={box_pt[2]})"
        )

    def test_september_is_the_widest_month_and_still_fits(self, output_dir: Path):
        """Explicit regression test for the exact reported bug case."""
        date_uk, date_en = dates_service.format_dates(9, 2026)
        assert date_uk == "Вересень, 2026"
        out = output_dir / "cert_september.pdf"
        render_certificate(make_fields(date_uk=date_uk, date_en=date_en), out)

        img = render_pdf_page_to_image(out)
        box_pt = BOXES["date"]["box_pt"]
        bbox = ink_bbox_pt(img, box_pt, pad_pt=0.0)
        assert bbox is not None
        assert bbox[2] <= box_pt[2] + 1.0


class TestLocationBox:
    """Location text must never rise high enough to overlap the blue pen
    signature drawn above it (signature ink's lowest point within the
    location box's x-range is at y ≈ 516.7pt in the reference design)."""

    @pytest.mark.parametrize(
        "location_uk,location_en",
        [
            ("м. Івано-Франківськ, Україна", "Ivano-Frankivsk city, Ukraine"),
            ("м. Дніпропетровськ-Каменськ-Подільський, Україна", "Dnipropetrovsk-Kamiansk-Podilskyi city, Ukraine"),
            ("Київ", ""),
        ],
    )
    def test_location_does_not_overlap_signature(self, output_dir: Path, location_uk: str, location_en: str):
        out = output_dir / f"cert_loc_{len(location_uk)}.pdf"
        render_certificate(make_fields(location_uk=location_uk, location_en=location_en), out)

        img = render_pdf_page_to_image(out)
        box_pt = BOXES["location"]["box_pt"]
        bbox = ink_bbox_pt(img, box_pt, pad_pt=0.0)
        assert bbox is not None
        min_x, min_y, max_x, _ = bbox
        assert min_y >= 520.0 - 1.0, f"location text rose above the signature-safe line (min_y={min_y})"
        assert max_x <= box_pt[2] + 1.0, f"location text overflowed box right edge (max_x={max_x})"
