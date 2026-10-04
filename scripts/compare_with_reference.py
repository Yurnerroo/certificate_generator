"""Integration/visual-comparison script (dev tool, not part of the app).

Generates one certificate PDF through the real rendering engine using the
exact same fields as the reference design ("Коваль Марія"), then opens both
the freshly generated PDF and the original reference PDF so a human can
compare them side by side.

Usage (from the project root, with the venv active):
    python scripts\\compare_with_reference.py            # generates + opens both PDFs
    python scripts\\compare_with_reference.py --no-open   # generates only (for automated/scripted iteration)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.certificate import CertificateFields, render_certificate  # noqa: E402

REFERENCE_PDF = PROJECT_ROOT / "design_assets" / "example_certificate_reference.pdf"
OUTPUT_DIR = PROJECT_ROOT / "scripts" / "_compare_output"
OUTPUT_PDF = OUTPUT_DIR / "generated_comparison.pdf"

FIELDS = CertificateFields(
    name_uk="Коваль Марія",
    name_en="Koval Mariia",
    title_uk="Стандарт роботи з клієнтами",
    title_en="Customer service standard",
    location_uk="м. Івано-Франківськ, Україна",
    location_en="Ivano-Frankivsk city, Ukraine",
    date_uk="Липень, 2026",
    date_en="July, 2026",
)


def main() -> None:
    if not REFERENCE_PDF.exists():
        print(f"ERROR: reference PDF not found at {REFERENCE_PDF}")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    render_certificate(FIELDS, OUTPUT_PDF)
    print(f"Generated: {OUTPUT_PDF}")
    print(f"Reference: {REFERENCE_PDF}")

    if "--no-open" not in sys.argv:
        os.startfile(str(REFERENCE_PDF))  # noqa: S606 - local dev tool, Windows only
        os.startfile(str(OUTPUT_PDF))


if __name__ == "__main__":
    main()
