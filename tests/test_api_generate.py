"""Integration tests for the /api/generate HTTP endpoint (app/main.py)."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

from conftest import get_pdf_page_count

client = TestClient(app)


def base_payload(default_folder: Path, **overrides) -> dict:
    payload = {
        "recipients": [{"name_uk": "Марук Надія", "name_en": "Maruk Nadiia"}],
        "title_uk": "Стандарт роботи з клієнтами",
        "title_en": "Customer service standard",
        "location_uk": "м. Івано-Франківськ, Україна",
        "location_en": "Ivano-Frankivsk city, Ukraine",
        "month": 7,
        "year": 2026,
        "output_folder": str(default_folder),
    }
    payload.update(overrides)
    return payload

class TestHappyPath:
    def test_single_recipient_generates_one_pdf(self, output_dir: Path):
        resp = client.post("/api/generate", json=base_payload(output_dir))
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["files"]) == 1
        pdf_path = output_dir / data["files"][0]
        assert pdf_path.exists()
        assert get_pdf_page_count(pdf_path) == 1

    def test_multiple_recipients_one_to_one_mixed_translation(self, output_dir: Path):
        """One recipient supplies their own English name; another leaves it
        blank and must fall back to automatic transliteration."""
        payload = base_payload(
            output_dir,
            recipients=[
                {"name_uk": "Марук Надія", "name_en": "Custom Spelling"},
                {"name_uk": "Зданевич Юрій", "name_en": ""},
            ],
        )
        resp = client.post("/api/generate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["files"]) == 2
        # The custom English spelling should be reflected in the filename of
        # the first recipient (proves per-recipient values aren't mixed up).
        assert any("Custom_Spelling" in f for f in data["files"])
        assert any("Zdanevych" in f or "Zdanevich" in f for f in data["files"])

    def test_recipient_with_blank_name_is_skipped(self, output_dir: Path):
        payload = base_payload(
            output_dir,
            recipients=[
                {"name_uk": "Марук Надія", "name_en": ""},
                {"name_uk": "   ", "name_en": "should be ignored"},
            ],
        )
        resp = client.post("/api/generate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["files"]) == 1

    def test_duplicate_names_get_unique_filenames(self, output_dir: Path):
        payload = base_payload(
            output_dir,
            recipients=[
                {"name_uk": "Марук Надія", "name_en": ""},
                {"name_uk": "Марук Надія", "name_en": ""},
            ],
        )
        resp = client.post("/api/generate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["files"]) == 2
        assert len(set(data["files"])) == 2  # no filename collisions
        for f in data["files"]:
            assert (output_dir / f).exists()

    def test_output_folder_is_created_if_missing(self, output_dir: Path):
        nested = output_dir / "does" / "not" / "exist" / "yet"
        resp = client.post("/api/generate", json=base_payload(nested))
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert nested.exists()


class TestValidationErrors:
    def test_empty_recipients_list_returns_400(self, output_dir: Path):
        resp = client.post("/api/generate", json=base_payload(output_dir, recipients=[]))
        assert resp.status_code == 400
        assert resp.json()["success"] is False

    def test_all_blank_recipient_names_returns_400(self, output_dir: Path):
        resp = client.post(
            "/api/generate",
            json=base_payload(output_dir, recipients=[{"name_uk": "   ", "name_en": ""}]),
        )
        assert resp.status_code == 400

    def test_missing_title_uk_returns_400(self, output_dir: Path):
        resp = client.post("/api/generate", json=base_payload(output_dir, title_uk=""))
        assert resp.status_code == 400

    def test_missing_location_uk_returns_400(self, output_dir: Path):
        resp = client.post("/api/generate", json=base_payload(output_dir, location_uk=""))
        assert resp.status_code == 400

    def test_missing_output_folder_returns_400(self, output_dir: Path):
        resp = client.post("/api/generate", json=base_payload(output_dir, output_folder=""))
        assert resp.status_code == 400

    def test_invalid_month_returns_400(self, output_dir: Path):
        resp = client.post("/api/generate", json=base_payload(output_dir, month=13))
        assert resp.status_code == 400

    def test_missing_recipients_field_returns_422(self, output_dir: Path):
        """Malformed payload (missing a required field entirely) should fail
        FastAPI/pydantic validation before reaching our own checks."""
        payload = base_payload(output_dir)
        del payload["recipients"]
        resp = client.post("/api/generate", json=payload)
        assert resp.status_code == 422


class TestTranslationFallback:
    def test_blank_title_en_and_location_en_do_not_crash(self, output_dir: Path):
        """When the optional English fields are left blank, the backend must
        attempt auto-translation and degrade gracefully (with a warning)
        rather than failing, even with no network access."""
        payload = base_payload(output_dir, title_en="", location_en="")
        resp = client.post("/api/generate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["files"]) == 1
