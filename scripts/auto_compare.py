"""Automated, code-driven 1:1 comparison between our generated certificate
and the reference example PDF -- no human screenshot-eyeballing required on
every iteration.

Rasterizes BOTH pdfs with the identical renderer (PyMuPDF/MuPDF) at the
template's native 300 DPI, then reports, fully programmatically:

  1. Whole-page pixel diff stats (mean/max abs difference, % of pixels that
     differ beyond a tolerance) + a saved diff-heatmap PNG.
  2. Dominant-color comparison in the static purple decoration area
     (frequency-count over a grid, robust to stripes/text/icons) -- tells us
     objectively whether the ICC-tagging color fix is converging.
  3. Per dynamic text box (name/title/location/date): crops both pages to
     the box, saves a stacked ref-vs-generated PNG for visual follow-up, AND
     measures the actual UK/EN vertical ink-gap in pixels (row-wise "has dark
     pixel" scanning) for both renders, converts back to pt, and reports the
     delta -- tells us objectively whether the spacing fix is converging.

This script is meant to be re-run after every code change, as a fast,
objective proxy before asking the user to eyeball a fresh screenshot.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_PDF = PROJECT_ROOT / "design_assets" / "example_certificate_reference.pdf"
GENERATED_PDF = PROJECT_ROOT / "scripts" / "_compare_output" / "generated_comparison.pdf"
OUT_DIR = PROJECT_ROOT / "scripts" / "_compare_output"
LAYOUT_PATH = PROJECT_ROOT / "design_assets" / "layout_spec.json"

DPI = 300
ZOOM = DPI / 72.0


def render_page(pdf_path: Path) -> Image.Image:
    doc = fitz.open(pdf_path)
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()
    return img


def whole_page_diff(ref_img: Image.Image, gen_img: Image.Image) -> tuple[float, int, float]:
    ref = np.asarray(ref_img.convert("RGB"), dtype=np.int16)
    gen_img_matched = gen_img
    if ref_img.size != gen_img.size:
        gen_img_matched = gen_img.resize(ref_img.size)
    gen = np.asarray(gen_img_matched.convert("RGB"), dtype=np.int16)
    diff = np.abs(ref - gen)
    mean_diff = float(diff.mean())
    max_diff = int(diff.max())
    pct_over_10 = float((diff.max(axis=2) > 10).mean() * 100)
    heat = diff.max(axis=2).clip(0, 255).astype(np.uint8)
    Image.fromarray(heat).save(OUT_DIR / "diff_heatmap.png")
    return mean_diff, max_diff, pct_over_10


def dominant_colors(img: Image.Image, box_px: tuple[int, int, int, int], n: int = 5, step: int = 6):
    crop = img.crop(box_px)
    counter: Counter = Counter()
    px = crop.load()
    for yy in range(0, crop.height, step):
        for xx in range(0, crop.width, step):
            counter[px[xx, yy]] += 1
    return counter.most_common(n)


def measure_ink_runs(img: Image.Image, box_px: tuple[int, int, int, int], dark_threshold: int = 150):
    """Return contiguous (start_row, end_row) ink-bearing row ranges within box_px."""
    crop = np.asarray(img.crop(box_px).convert("L"))
    has_ink = (crop < dark_threshold).any(axis=1)
    runs = []
    in_run = False
    start = 0
    for i, v in enumerate(has_ink):
        if v and not in_run:
            start = i
            in_run = True
        elif not v and in_run:
            runs.append((start, i - 1))
            in_run = False
    if in_run:
        runs.append((start, len(has_ink) - 1))
    return runs


def pt_to_px(box_pt: list[float]) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box_pt
    return (int(x0 * ZOOM), int(y0 * ZOOM), int(x1 * ZOOM), int(y1 * ZOOM))


def main() -> None:
    if not GENERATED_PDF.exists():
        raise SystemExit(
            f"Generated PDF not found at {GENERATED_PDF}. Run scripts/compare_with_reference.py first."
        )
    layout = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))

    ref_img = render_page(REFERENCE_PDF)
    gen_img = render_page(GENERATED_PDF)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ref_img.save(OUT_DIR / "ref_raster.png")
    gen_img.save(OUT_DIR / "gen_raster.png")

    print("=== Whole-page pixel diff ===")
    mean_diff, max_diff, pct_over_10 = whole_page_diff(ref_img, gen_img)
    print(f"mean abs diff: {mean_diff:.2f}/255, max: {max_diff}, pixels with >10 diff: {pct_over_10:.2f}%")
    print(f"(heatmap saved: {OUT_DIR / 'diff_heatmap.png'})")

    print("\n=== Dominant colors: purple panel area (left 30% of page) ===")
    w, h = ref_img.size
    purple_box = (0, 0, int(w * 0.30), h)
    print("reference top colors:", dominant_colors(ref_img, purple_box))
    print("generated top colors: ", dominant_colors(gen_img, purple_box))

    print("\n=== Dynamic box UK/EN vertical gap (measured from rendered pixels) ===")
    for box_name, box_spec in layout["dynamic_boxes"].items():
        box_px = pt_to_px(box_spec["box_pt"])
        ref_runs = measure_ink_runs(ref_img, box_px)
        gen_runs = measure_ink_runs(gen_img, box_px)

        def gap_pt(runs):
            if len(runs) < 2:
                return None
            return round((runs[-1][0] - runs[-2][1]) / ZOOM, 2)

        print(f"{box_name}: ref_gap={gap_pt(ref_runs)}pt (runs={ref_runs})  "
              f"gen_gap={gap_pt(gen_runs)}pt (runs={gen_runs})")

        ref_crop = ref_img.crop(box_px)
        gen_crop = gen_img.crop(box_px)
        combo = Image.new("RGB", (max(ref_crop.width, gen_crop.width), ref_crop.height + gen_crop.height + 10), "white")
        combo.paste(ref_crop, (0, 0))
        combo.paste(gen_crop, (0, ref_crop.height + 10))
        combo.save(OUT_DIR / f"box_{box_name}_compare.png")

    print(f"\nPer-box stacked crops saved to {OUT_DIR} (box_<name>_compare.png, reference on top).")


if __name__ == "__main__":
    main()
