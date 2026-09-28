"""Shared pytest fixtures for the certificate generator's integration test suite."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterator

import fitz  # PyMuPDF -- used only by tests, to rasterize/inspect generated PDFs
import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESIGN_ASSETS_DIR = PROJECT_ROOT / "design_assets"
TESTS_OUTPUT_DIR = Path(__file__).resolve().parent / "output"

with open(DESIGN_ASSETS_DIR / "layout_spec.json", "r", encoding="utf-8") as _f:
    LAYOUT_SPEC: dict = json.load(_f)

DPI = LAYOUT_SPEC["page"]["template_png_dpi"]
PT_TO_PX = DPI / 72.0


@pytest.fixture(scope="session", autouse=True)
def _clean_output_dir() -> Iterator[None]:
    """Start each test run with a fresh tests/output/ directory of generated PDFs."""
    if TESTS_OUTPUT_DIR.exists():
        shutil.rmtree(TESTS_OUTPUT_DIR)
    TESTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture()
def output_dir(request: pytest.FixtureRequest) -> Path:
    """A dedicated, per-test subfolder under tests/output/ to keep generated PDFs
    from different test cases separated and easy to browse afterwards.

    Parametrized test IDs can contain arbitrary Unicode/punctuation (Cyrillic
    names, apostrophes, etc.) which are not valid in Windows folder names, so
    the raw node name is replaced with a short, filesystem-safe hash instead.
    """
    import hashlib

    test_func_name = request.node.name.split("[")[0]
    has_params = "[" in request.node.name
    if has_params:
        digest = hashlib.sha1(request.node.name.encode("utf-8")).hexdigest()[:10]
        folder = TESTS_OUTPUT_DIR / f"{test_func_name}_{digest}"
    else:
        folder = TESTS_OUTPUT_DIR / test_func_name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def render_pdf_page_to_image(pdf_path: Path, dpi: float = DPI) -> Image.Image:
    """Rasterize page 1 of a PDF to a Pillow RGB image at the given DPI."""
    doc = fitz.open(str(pdf_path))
    try:
        pix = doc[0].get_pixmap(dpi=int(dpi))
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    finally:
        doc.close()


def get_pdf_page_count(pdf_path: Path) -> int:
    doc = fitz.open(str(pdf_path))
    try:
        return doc.page_count
    finally:
        doc.close()


def get_pdf_page_size_pt(pdf_path: Path) -> tuple[float, float]:
    doc = fitz.open(str(pdf_path))
    try:
        rect = doc[0].rect
        return (rect.width, rect.height)
    finally:
        doc.close()


def count_background_pixel_diffs(
    generated: Image.Image,
    reference: Image.Image,
    ignore_boxes_pt: list[list[float]],
    pad_pt: float = 4.0,
) -> tuple[int, int]:
    """Compare two same-size RGB renders pixel-by-pixel, ignoring the given
    dynamic box_pt regions (plus a small pad). Returns (max_abs_channel_diff,
    differing_pixel_count) over everything OUTSIDE those regions -- i.e. the
    static background/decorations, which must stay pixel-identical to the
    reference design (regression guard for the lossy-JPEG color-shift bug).
    """
    import numpy as np

    assert generated.size == reference.size, (generated.size, reference.size)
    gen_arr = np.array(generated, dtype=np.int16)
    ref_arr = np.array(reference, dtype=np.int16)

    mask = np.ones(gen_arr.shape[:2], dtype=bool)
    for box_pt in ignore_boxes_pt:
        x0 = max(0, int((box_pt[0] - pad_pt) * PT_TO_PX))
        y0 = max(0, int((box_pt[1] - pad_pt) * PT_TO_PX))
        x1 = min(gen_arr.shape[1], int((box_pt[2] + pad_pt) * PT_TO_PX))
        y1 = min(gen_arr.shape[0], int((box_pt[3] + pad_pt) * PT_TO_PX))
        mask[y0:y1, x0:x1] = False

    diff = np.abs(gen_arr - ref_arr).max(axis=2)
    masked_diff = diff[mask]
    max_diff = int(masked_diff.max()) if masked_diff.size else 0
    differing = int((masked_diff > 0).sum())
    return max_diff, differing


def ink_bbox_pt(image: Image.Image, box_pt: list[float], pad_pt: float = 6.0) -> tuple[float, float, float, float] | None:
    """Scan the given box_pt region (plus a small pad) for non-white pixels and
    return the tight bounding box (in pt) of any drawn ink, or None if empty."""
    x0 = int((box_pt[0] - pad_pt) * PT_TO_PX)
    y0 = int((box_pt[1] - pad_pt) * PT_TO_PX)
    x1 = int((box_pt[2] + pad_pt) * PT_TO_PX)
    y1 = int((box_pt[3] + pad_pt) * PT_TO_PX)
    px = image.load()
    w, h = image.size
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)

    min_x = min_y = 10**9
    max_x = max_y = -1
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = px[x, y]
            if r < 250 or g < 250 or b < 250:
                min_x, max_x = min(min_x, x), max(max_x, x)
                min_y, max_y = min(min_y, y), max(max_y, y)
    if max_y < 0:
        return None
    return (min_x / PT_TO_PX, min_y / PT_TO_PX, max_x / PT_TO_PX, max_y / PT_TO_PX)


def ink_row_bands_pt(image: Image.Image, box_pt: list[float], pad_pt: float = 6.0) -> list[tuple[float, float]]:
    """Scan the given box_pt region row-by-row for ink and return the list of
    contiguous (top_pt, bottom_pt) bands separated by blank rows -- e.g. the
    Ukrainian line(s) form one band, the gap is blank, and the English line
    forms the next band. Used to measure each language's rendered text height
    independently without reaching into the renderer's private internals."""
    x0 = int((box_pt[0] - pad_pt) * PT_TO_PX)
    y0 = int((box_pt[1] - pad_pt) * PT_TO_PX)
    x1 = int((box_pt[2] + pad_pt) * PT_TO_PX)
    y1 = int((box_pt[3] + pad_pt) * PT_TO_PX)
    px = image.load()
    w, h = image.size
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)

    row_has_ink = []
    for y in range(y0, y1):
        has_ink = False
        for x in range(x0, x1):
            r, g, b = px[x, y]
            if r < 250 or g < 250 or b < 250:
                has_ink = True
                break
        row_has_ink.append(has_ink)

    bands: list[tuple[int, int]] = []
    start = None
    for i, v in enumerate(row_has_ink):
        if v and start is None:
            start = i
        elif not v and start is not None:
            bands.append((start, i - 1))
            start = None
    if start is not None:
        bands.append((start, len(row_has_ink) - 1))

    return [((y0 + s) / PT_TO_PX, (y0 + e) / PT_TO_PX) for s, e in bands]
