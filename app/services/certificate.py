"""Certificate PDF rendering engine.

Composites the dynamic text fields (name, training title, location, date --
each in Ukrainian and English) onto the pre-baked
`design_assets/certificate_template.png` background, using the exact box
coordinates/fonts/colors from `design_assets/layout_spec.json`. Everything
else on the certificate (logo, headings, QR code, signature, decorations) is
already pixel-perfect in the template PNG and is never redrawn.

Auto-fit rule (per layout_spec.json's "sizing_rule"): for each dynamic box,
the Ukrainian and English lines are fitted independently -- first by
word-wrapping at the base font size, then, if that still doesn't fit the
space available, by shrinking the font size in small steps -- so text never
overflows its box or crosses into the decorative background.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import img2pdf
import pikepdf
from PIL import Image, ImageDraw, ImageFont

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ASSETS_DIR = _PROJECT_ROOT / "design_assets"
_FONTS_DIR = _ASSETS_DIR / "fonts"

# The reference design's PDF draws its decorations as vector shapes tagged
# with this exact sRGB ICC profile (extracted once from that file). Browser
# PDF viewers (e.g. Chrome/Edge's PDFium) color-manage ICC-tagged content
# differently than untagged "DeviceRGB" images, which made our raster-based
# certificate visibly mismatch the reference's purple/yellow even though the
# underlying RGB numbers were close. Tagging our output image with the same
# profile makes the viewer apply an identical transform to both, so what the
# user sees on screen actually matches -- not just the raw pixel values.
_SRGB_ICC_PROFILE = (_ASSETS_DIR / "srgb_icc_profile.icc").read_bytes()

with open(_ASSETS_DIR / "layout_spec.json", "r", encoding="utf-8") as _f:
    LAYOUT: dict = json.load(_f)

_DPI: float = LAYOUT["page"]["template_png_dpi"]
PT_TO_PX: float = _DPI / 72.0
TEXT_COLOR: str = LAYOUT["text_color"]

_FONT_FILES: dict[str, str] = LAYOUT["fonts"]
_MIN_FONT_PT = 7.0          # absolute floor so text never becomes illegible
_FONT_STEP_PT = 0.5
_LINE_SPACING = 1.18        # multiplier applied to font ascent+descent
# Vertical gap between the UK and EN sub-blocks. Measured directly from the
# reference PDF's real text bounding boxes (layout_spec.json's orig_bbox_pt):
# name 178.2->180.1 (~1.9pt), title 393.0->396.0 (~3.0pt), location
# 533.1->534.2 (~1.1pt), date 533.2->534.2 (~1.0pt). 2.0pt matches all four
# far more closely than the previous 6.0pt, which rendered a visibly bigger
# gap than the original design.
_GAP_PT = 2.0

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
_template_image: Image.Image | None = None


def _reference_gap_pt(lines_spec: list[dict]) -> float:
    """Compute the true UK->EN ink-to-ink gap (in pt) for one dynamic box from
    its ground-truth orig_bbox_pt measurements in layout_spec.json.

    These bboxes were measured directly from the real reference PDF's text
    positions, so they capture the designer's actual tight spacing. Our own
    nominal font-metric line height (ascent+descent) includes extra padding
    that isn't inked for most Cyrillic/Latin text, which made the gap look
    visibly larger than the reference even with a small `_GAP_PT`. Using this
    measured value as the *rendering* target (see `_render_box`'s ink-bbox
    positioning) instead of just a flat constant reproduces the original
    spacing far more closely.
    """
    uk_spec = next((s for s in lines_spec if s["lang"] == "uk"), None)
    en_spec = next((s for s in lines_spec if s["lang"] == "en"), None)
    if not uk_spec or not en_spec:
        return _GAP_PT
    uk_bbox = uk_spec.get("orig_bbox_line2_pt") or uk_spec.get("orig_bbox_pt")
    en_bbox = en_spec.get("orig_bbox_pt")
    if not uk_bbox or not en_bbox:
        return _GAP_PT
    return max(0.0, en_bbox[1] - uk_bbox[3])


def _reference_top_offset_pt(box_pt: list[float], lines_spec: list[dict]) -> float | None:
    """How far down from the box's top edge the reference design's first
    (Ukrainian) line's ink actually starts, in pt.

    Centering the whole UK+EN block inside its (often much taller, to leave
    room for long names/titles) box looked visibly off vs. the reference,
    which anchors content a fixed distance from the box top instead. Reusing
    the same ground-truth orig_bbox_pt measurements already used for the gap
    gives us that exact anchor for the common case (short text, same line
    count as the reference); callers should still fall back to centering if
    honoring it would overflow the box.
    """
    uk_spec = next((s for s in lines_spec if s["lang"] == "uk"), None)
    if not uk_spec:
        return None
    uk_bbox = uk_spec.get("orig_bbox_line1_pt") or uk_spec.get("orig_bbox_pt")
    if not uk_bbox:
        return None
    return uk_bbox[1] - box_pt[1]


@dataclass
class CertificateFields:
    name_uk: str
    title_uk: str
    location_uk: str
    date_uk: str
    name_en: str = ""
    title_en: str = ""
    location_en: str = ""
    date_en: str = ""


def _resolve_font_file(font_key: str) -> str:
    """Map a layout_spec 'font' value to an actual bundled font file."""
    if font_key in _FONT_FILES:
        return _FONT_FILES[font_key]
    # e.g. name.en's "regular_bold_look_ok" -- the spec's own note clarifies
    # the real PDF actually used the bold face there too, just smaller.
    return _FONT_FILES["bold"]


def _get_font(font_key: str, size_px: int) -> ImageFont.FreeTypeFont:
    size_px = max(1, int(round(size_px)))
    cache_key = (font_key, size_px)
    if cache_key not in _font_cache:
        font_path = _FONTS_DIR / _resolve_font_file(font_key)
        _font_cache[cache_key] = ImageFont.truetype(str(font_path), size_px)
    return _font_cache[cache_key]


def _line_height(font: ImageFont.FreeTypeFont) -> float:
    ascent, descent = font.getmetrics()
    return (ascent + descent) * _LINE_SPACING


def _get_template_image() -> Image.Image:
    global _template_image
    if _template_image is None:
        img = Image.open(_ASSETS_DIR / LAYOUT["page"]["template_png"])
        if img.mode == "RGBA":
            background = Image.new("RGB", img.size, "white")
            background.paste(img, mask=img.split()[3])
            img = background
        else:
            img = img.convert("RGB")
        _template_image = img
    return _template_image


def _pt_box_to_px(box_pt: list[float]) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = box_pt
    return (x0 * PT_TO_PX, y0 * PT_TO_PX, x1 * PT_TO_PX, y1 * PT_TO_PX)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width_px: float) -> list[str]:
    """Greedy word-wrap; falls back to character-splitting for an over-wide single word."""
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width_px:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)

    final_lines: list[str] = []
    for line in lines:
        if " " in line or draw.textlength(line, font=font) <= max_width_px:
            final_lines.append(line)
        else:
            final_lines.extend(_char_split(draw, line, font, max_width_px))
    return final_lines


def _char_split(draw: ImageDraw.ImageDraw, word: str, font: ImageFont.FreeTypeFont, max_width_px: float) -> list[str]:
    chunks: list[str] = []
    current = ""
    for ch in word:
        candidate = current + ch
        if not current or draw.textlength(candidate, font=font) <= max_width_px:
            current = candidate
        else:
            chunks.append(current)
            current = ch
    if current:
        chunks.append(current)
    return chunks or [word]


@dataclass
class _FitResult:
    font: ImageFont.FreeTypeFont
    lines: list[str]
    line_height: float
    block_height: float


def _fit_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_key: str,
    base_size_pt: float,
    max_width_px: float,
    max_height_px: float,
) -> _FitResult:
    """Wrap `text` at base size; shrink font in steps until it fits max_height_px."""
    if not text:
        font = _get_font(font_key, max(1, int(round(base_size_pt * PT_TO_PX))))
        return _FitResult(font, [], _line_height(font), 0.0)

    size_pt = base_size_pt
    last: _FitResult | None = None
    while size_pt >= _MIN_FONT_PT:
        size_px = base_size_pt_to_px(size_pt)
        font = _get_font(font_key, size_px)
        lines = _wrap_text(draw, text, font, max_width_px)
        lh = _line_height(font)
        block_height = lh * len(lines)
        fits_width = all(draw.textlength(ln, font=font) <= max_width_px for ln in lines)
        last = _FitResult(font, lines, lh, block_height)
        if fits_width and block_height <= max_height_px:
            return last
        size_pt -= _FONT_STEP_PT

    # Last resort: keep the smallest size, but truncate lines so we never
    # draw outside the box vertically.
    assert last is not None
    max_lines = max(1, int(max_height_px // last.line_height)) if last.line_height else len(last.lines)
    truncated_lines = last.lines[:max_lines]
    return _FitResult(last.font, truncated_lines, last.line_height, last.line_height * len(truncated_lines))


def base_size_pt_to_px(size_pt: float) -> int:
    return max(1, int(round(size_pt * PT_TO_PX)))


def _render_box(
    draw: ImageDraw.ImageDraw,
    box_pt: list[float],
    lines_spec: list[dict],
    texts: dict[str, str],
) -> None:
    x0, y0, x1, y1 = _pt_box_to_px(box_pt)
    max_width = x1 - x0
    box_height = y1 - y0
    gap_px = _GAP_PT * PT_TO_PX
    min_size_px = base_size_pt_to_px(_MIN_FONT_PT)

    spec_by_lang = {spec["lang"]: spec for spec in lines_spec}

    uk_budget_fraction = 0.7
    fits: dict[str, _FitResult] = {}
    for _ in range(6):
        remaining_height = box_height
        active_langs = [lang for lang in spec_by_lang if texts.get(lang, "").strip() != ""]
        if not active_langs:
            fits = {}
            break

        ok = True
        used_height = 0.0
        for i, lang in enumerate(active_langs):
            spec = spec_by_lang[lang]
            font_key = spec["font"] if spec["font"] in _FONT_FILES else "bold"
            is_last = i == len(active_langs) - 1
            if is_last:
                budget = remaining_height
            else:
                budget = remaining_height * uk_budget_fraction

            base_size_pt = spec["base_size_pt"]
            if lang == "en" and "uk" in fits:
                # Keep the English line proportionally smaller than the Ukrainian
                # line's *actual* rendered size (not just its own base size), so
                # long Ukrainian text that has to shrink a lot doesn't leave the
                # English translation looking the same size or larger.
                uk_spec = spec_by_lang.get("uk", {})
                uk_base_pt = uk_spec.get("base_size_pt") or base_size_pt
                uk_actual_pt = fits["uk"].font.size / PT_TO_PX
                ratio = min(base_size_pt / uk_base_pt, 0.95) if uk_base_pt else 0.5
                base_size_pt = min(base_size_pt, uk_actual_pt * ratio)

            fit = _fit_block(draw, texts[lang], font_key, base_size_pt, max_width, max(budget, min_size_px))
            fits[lang] = fit
            consumed = fit.block_height + (gap_px if not is_last else 0.0)
            remaining_height -= consumed
            used_height += consumed
            if remaining_height < 0:
                ok = False
        if ok and used_height <= box_height + 0.5:
            break
        uk_budget_fraction -= 0.1
        if uk_budget_fraction < 0.2:
            uk_budget_fraction = 0.2

    if not fits:
        return

    active_langs = [spec["lang"] for spec in lines_spec if spec["lang"] in fits]
    target_gap_px = _reference_gap_pt(lines_spec) * PT_TO_PX
    total_height = sum(fits[lang].block_height for lang in active_langs) + target_gap_px * max(
        0, len(active_langs) - 1
    )

    # Prefer anchoring the block exactly where the reference design starts it
    # (measured from the real reference PDF), rather than centering it inside
    # the box. The box is deliberately taller than the shortest possible text
    # so long names/titles have room to wrap without overflowing, but for
    # typical (shorter) text that leaves a lot of empty space below -- pure
    # centering then starts the text noticeably lower than the reference.
    # Fall back to centering only if that anchor would overflow the box
    # (e.g. unusually long text needing extra wrapped lines).
    y_cursor = None
    anchor_offset_pt = _reference_top_offset_pt(box_pt, lines_spec)
    if anchor_offset_pt is not None and active_langs and fits[active_langs[0]].lines:
        first_fit = fits[active_langs[0]]
        _, top_ink_first, _, _ = first_fit.font.getbbox(first_fit.lines[0])
        candidate_y0 = y0 + anchor_offset_pt * PT_TO_PX - top_ink_first
        if candidate_y0 >= y0 - 0.5 and candidate_y0 + total_height <= y1 + 0.5:
            y_cursor = candidate_y0
    if y_cursor is None:
        y_cursor = y0 + max(0.0, (box_height - total_height) / 2.0)

    prev_block_ink_bottom: float | None = None
    for block_idx, lang in enumerate(active_langs):
        fit = fits[lang]
        for line_idx, line in enumerate(fit.lines):
            if block_idx > 0 and line_idx == 0 and prev_block_ink_bottom is not None:
                # Reposition this block's first line precisely: nominal
                # per-line advancement (ascent+descent) includes unused
                # padding above/below the actual glyph ink, which otherwise
                # makes the UK->EN gap look much bigger than the reference.
                # Use the font's real ink bbox so the *visible* gap matches
                # the reference's measured spacing, not just the nominal one.
                _, top_ink, _, _ = fit.font.getbbox(line)
                y_cursor = prev_block_ink_bottom + target_gap_px - top_ink
            draw.text((x0, y_cursor), line, font=fit.font, fill=TEXT_COLOR)
            _, _, _, bottom_ink = fit.font.getbbox(line)
            prev_block_ink_bottom = y_cursor + bottom_ink
            y_cursor += fit.line_height


def render_certificate(fields: CertificateFields, output_pdf_path: Path) -> None:
    """Render a single certificate PDF for one recipient."""
    img = _get_template_image().copy()
    draw = ImageDraw.Draw(img)

    boxes = LAYOUT["dynamic_boxes"]
    field_map = {
        "name": ("name_uk", "name_en"),
        "title": ("title_uk", "title_en"),
        "location": ("location_uk", "location_en"),
        "date": ("date_uk", "date_en"),
    }

    for box_name, (uk_attr, en_attr) in field_map.items():
        box_spec = boxes[box_name]
        texts = {"uk": getattr(fields, uk_attr) or "", "en": getattr(fields, en_attr) or ""}
        _render_box(draw, box_spec["box_pt"], box_spec["lines"], texts)

    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)

    # Pillow's built-in `Image.save(..., "PDF")` re-encodes RGB images as lossy
    # JPEG (DCTDecode), which subtly shifts the exact background colors/edges.
    # To keep the certificate's colors pixel-identical to the source design,
    # encode the composited page as PNG (lossless) in memory, then wrap that
    # losslessly (FlateDecode) into the final PDF via img2pdf.
    png_buffer = BytesIO()
    img.save(png_buffer, "PNG")
    png_bytes = png_buffer.getvalue()

    layout_fun = img2pdf.get_fixed_dpi_layout_fun((_DPI, _DPI))
    pdf_bytes = img2pdf.convert(png_bytes, layout_fun=layout_fun)
    pdf_bytes = _tag_page_image_with_srgb_icc(pdf_bytes)
    output_pdf_path.write_bytes(pdf_bytes)


def _tag_page_image_with_srgb_icc(pdf_bytes: bytes) -> bytes:
    """Re-tag the page's image XObject(s) with the reference design's exact
    sRGB ICC profile instead of img2pdf's default untagged DeviceRGB.

    Without this, PDF viewers that color-manage ICC-tagged content (as the
    reference PDF's vector shapes are) but not plain DeviceRGB images render
    the *same* nominal RGB values as visibly different colors on screen --
    which is what caused the certificate's purple/yellow to look off even
    after the pixel values were corrected to match.
    """
    with pikepdf.open(BytesIO(pdf_bytes)) as pdf:
        icc_stream = pikepdf.Stream(pdf, _SRGB_ICC_PROFILE)
        icc_stream.N = 3
        icc_stream.Alternate = pikepdf.Name("/DeviceRGB")
        icc_colorspace = pikepdf.Array([pikepdf.Name("/ICCBased"), icc_stream])

        for page in pdf.pages:
            xobjects = page.Resources.get("/XObject", {})
            for xobj in xobjects.values():
                if xobj.get("/Subtype") == pikepdf.Name("/Image") and xobj.get("/ColorSpace") == pikepdf.Name(
                    "/DeviceRGB"
                ):
                    xobj.ColorSpace = icc_colorspace

        out = BytesIO()
        pdf.save(out)
        return out.getvalue()
