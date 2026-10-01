"""One-off dev tool: recolor specific solid-fill colors in the baked
`design_assets/certificate_template.png` to match the reference PDF's exact
raw vector fill values.

Why: screenshot-based color sampling (used in earlier fixes) is lossy and
viewer-dependent -- different screenshots of the same reference PDF produced
different "true" purple values.

Note: the reference PDF's raw content-stream `scn` fill operand for the
purple panel is (0.04, 0.05, 0.69) -> naive 0-255 scaling gives (10, 13,
176). That value was tried first, but it does NOT match how the reference
actually renders: PyMuPDF rasterizes that same ICCBased fill to a visibly
lighter/less saturated (52, 36, 131), almost certainly because the page's
embedded ICC profile has a non-trivial tone curve (so raw component values
aren't a literal 0-1 -> 0-255 passthrough) and/or a semi-transparent overlay
sits across the panel. Since we can't cheaply replicate that profile/overlay
math on a flat raster, the pragmatic and empirically-verifiable target is
instead "what the SAME renderer (PyMuPDF, 300 DPI) measures as the
reference's dominant color" -- i.e. the output of
`scripts/auto_compare.py`'s dominant-color scan. That is reproducible, not
tied to any one screenshot/viewer, and is what we converge our template
toward below.

Usage (from the project root, with the venv active):
    python scripts\\recolor_template.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PNG = PROJECT_ROOT / "design_assets" / "certificate_template.png"

# (old_rgb, new_rgb, match_threshold) -- new_rgb values are the reference
# PDF's dominant colors as measured by PyMuPDF at 300 DPI (via
# scripts/auto_compare.py), i.e. what actually gets rendered on screen, not
# the raw (profile-transformed) content-stream fill operands.
RECOLORS = [
    ((55, 55, 156), (52, 36, 131), 60),   # purple panel (was PR#5's screenshot-estimated value)
    ((237, 227, 65), (237, 229, 65), 30),  # yellow accent shapes
]


def recolor(img: Image.Image, old_rgb, new_rgb, threshold) -> Image.Image:
    arr = np.asarray(img.convert("RGB")).astype(np.float32)
    old = np.array(old_rgb, dtype=np.float32)
    new = np.array(new_rgb, dtype=np.float32)
    delta = new - old
    dist = np.sqrt(((arr - old) ** 2).sum(axis=2))
    alpha = np.clip(1.0 - dist / threshold, 0.0, 1.0)
    recolored = arr.astype(np.float32) + alpha[..., None] * delta
    recolored = np.clip(recolored, 0, 255).astype(np.uint8)
    return Image.fromarray(recolored, mode="RGB")


def main() -> None:
    img = Image.open(TEMPLATE_PNG)
    had_alpha = img.mode == "RGBA"
    alpha_channel = img.split()[3] if had_alpha else None
    img = img.convert("RGB")

    for old_rgb, new_rgb, threshold in RECOLORS:
        img = recolor(img, old_rgb, new_rgb, threshold)

    if had_alpha:
        img = img.convert("RGBA")
        img.putalpha(alpha_channel)

    img.save(TEMPLATE_PNG)
    print(f"Recolored and saved: {TEMPLATE_PNG}")


if __name__ == "__main__":
    main()
