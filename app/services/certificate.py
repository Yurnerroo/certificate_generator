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
from PIL import Image, ImageDraw, ImageFont

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ASSETS_DIR = _PROJECT_ROOT / "design_assets"
_FONTS_DIR = _ASSETS_DIR / "fonts"

with open(_ASSETS_DIR / "layout_spec.json", "r", encoding="utf-8") as _f:
    LAYOUT: dict = json.load(_f)

_DPI: float = LAYOUT["page"]["template_png_dpi"]
PT_TO_PX: float = _DPI / 72.0
TEXT_COLOR: str = LAYOUT["text_color"]

_FONT_FILES: dict[str, str] = LAYOUT["fonts"]
_MIN_FONT_PT = 7.0          # absolute floor so text never becomes illegible
_FONT_STEP_PT = 0.5
_LINE_SPACING = 1.18        # multiplier applied to font ascent+descent
_GAP_PT = 6.0                # vertical gap between the UK and EN sub-blocks

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
_template_image: Image.Image | None = None


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
            fit = _fit_block(draw, texts[lang], font_key, spec["base_size_pt"], max_width, max(budget, min_size_px))
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
    total_height = sum(fits[lang].block_height for lang in active_langs) + gap_px * max(0, len(active_langs) - 1)
    y_cursor = y0 + max(0.0, (box_height - total_height) / 2.0)

    for lang in active_langs:
        fit = fits[lang]
        for line in fit.lines:
            draw.text((x0, y_cursor), line, font=fit.font, fill=TEXT_COLOR)
            y_cursor += fit.line_height
        y_cursor += gap_px


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
    output_pdf_path.write_bytes(pdf_bytes)
