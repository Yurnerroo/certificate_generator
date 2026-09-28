"""FastAPI application: local-only certificate generator web app."""
from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import List

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app import config
from app.services import dates as dates_service
from app.services.certificate import CertificateFields, render_certificate
from app.services.transliteration import transliterate_name
from app.services.translation import translate_uk_to_en

logger = logging.getLogger("certificate_generator")
logging.basicConfig(level=logging.INFO)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESIGN_ASSETS_DIR = PROJECT_ROOT / "design_assets"

app = FastAPI(title="Certificate Generator")

app.mount("/design_assets", StaticFiles(directory=str(DESIGN_ASSETS_DIR)), name="design_assets")
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "app" / "static")), name="static")

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _parse_lines(text: str) -> List[str]:
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def _sanitize_filename(text: str) -> str:
    text = (text or "").strip()
    text = _INVALID_FILENAME_CHARS.sub("", text)
    text = re.sub(r"\s+", "_", text)
    text = text.strip("_.")
    return text or "certificate"


class GenerateRequest(BaseModel):
    names_uk: str
    names_en: str = ""
    title_uk: str
    title_en: str = ""
    location_uk: str
    location_en: str = ""
    month: int
    year: int
    output_folder: str


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    import datetime

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "months": dates_service.month_choices(),
            "last_output_folder": config.get_last_output_folder(),
            "current_year": datetime.date.today().year,
            "current_month": datetime.date.today().month,
        },
    )


@app.post("/api/browse-folder")
async def browse_folder(request: Request):
    body = await request.json()
    initial_dir = body.get("current_path") or config.get_last_output_folder() or str(Path.home())

    import asyncio

    loop = asyncio.get_event_loop()
    try:
        path = await loop.run_in_executor(None, _pick_folder_dialog, initial_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Folder picker unavailable: %s", exc)
        return JSONResponse(
            {"path": None, "error": "Не вдалося відкрити діалог вибору папки на цій системі. Введіть шлях вручну."}
        )

    if not path:
        return JSONResponse({"path": None, "error": None})
    return JSONResponse({"path": path, "error": None})


def _pick_folder_dialog(initial_dir: str) -> str | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(
            initialdir=initial_dir if os.path.isdir(initial_dir) else str(Path.home()),
            title="Оберіть папку для збереження сертифікатів",
        )
    finally:
        root.destroy()
    return selected or None


@app.post("/api/open-folder")
async def open_folder(request: Request):
    body = await request.json()
    folder = body.get("path", "")
    if not folder or not os.path.isdir(folder):
        return JSONResponse({"success": False, "error": "Папка не знайдена."}, status_code=400)
    try:
        if sys.platform.startswith("win"):
            os.startfile(folder)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f'open "{folder}"')
        else:
            os.system(f'xdg-open "{folder}"')
        return JSONResponse({"success": True})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@app.post("/api/generate")
async def generate(payload: GenerateRequest):
    warnings: List[str] = []

    names_uk = _parse_lines(payload.names_uk)
    if not names_uk:
        return JSONResponse(
            {"success": False, "error": "Список імен отримувачів порожній. Введіть хоча б одне ім'я."},
            status_code=400,
        )

    names_en_raw = _parse_lines(payload.names_en)
    if names_en_raw:
        if len(names_en_raw) != len(names_uk):
            return JSONResponse(
                {
                    "success": False,
                    "error": (
                        f"Кількість імен українською ({len(names_uk)}) не збігається з кількістю "
                        f"імен англійською ({len(names_en_raw)}). Перевірте обидва списки — "
                        f"кожен рядок має відповідати одному й тому ж отримувачу."
                    ),
                },
                status_code=400,
            )
        names_en = names_en_raw
    else:
        names_en = [transliterate_name(n) for n in names_uk]

    title_uk = payload.title_uk.strip()
    if not title_uk:
        return JSONResponse({"success": False, "error": "Поле «Назва тренінгу» є обов'язковим."}, status_code=400)

    location_uk = payload.location_uk.strip()
    if not location_uk:
        return JSONResponse({"success": False, "error": "Поле «Локація» є обов'язковим."}, status_code=400)

    title_en = payload.title_en.strip()
    if not title_en:
        result = translate_uk_to_en(title_uk, "Назва тренінгу")
        title_en = result.text
        if result.warning:
            warnings.append(result.warning)

    location_en = payload.location_en.strip()
    if not location_en:
        result = translate_uk_to_en(location_uk, "Локація")
        location_en = result.text
        if result.warning:
            warnings.append(result.warning)

    try:
        date_uk, date_en = dates_service.format_dates(payload.month, payload.year)
    except ValueError as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)

    output_folder_raw = (payload.output_folder or "").strip()
    if not output_folder_raw:
        return JSONResponse({"success": False, "error": "Оберіть або введіть папку для збереження сертифікатів."}, status_code=400)

    output_dir = Path(output_folder_raw).expanduser()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        probe = output_dir / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        return JSONResponse(
            {"success": False, "error": f"Не вдалося створити або записати у папку «{output_folder_raw}»: {exc}"},
            status_code=400,
        )

    generated_files: List[str] = []
    used_filenames: set[str] = set()
    for idx, (name_uk, name_en) in enumerate(zip(names_uk, names_en), start=1):
        fields = CertificateFields(
            name_uk=name_uk,
            name_en=name_en,
            title_uk=title_uk,
            title_en=title_en,
            location_uk=location_uk,
            location_en=location_en,
            date_uk=date_uk,
            date_en=date_en,
        )
        base_name = _sanitize_filename(name_en or transliterate_name(name_uk))
        filename = f"{idx:02d}_{base_name}.pdf"
        # Guard against duplicate filenames (e.g. two recipients with the same name).
        candidate = filename
        suffix = 1
        while candidate in used_filenames:
            suffix += 1
            candidate = f"{idx:02d}_{base_name}_{suffix}.pdf"
        filename = candidate
        used_filenames.add(filename)

        output_path = output_dir / filename
        try:
            render_certificate(fields, output_path)
            generated_files.append(filename)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to render certificate for %s", name_uk)
            warnings.append(f"Не вдалося згенерувати сертифікат для «{name_uk}»: {exc}")

    config.set_last_output_folder(str(output_dir))

    return JSONResponse(
        {
            "success": True,
            "output_folder": str(output_dir),
            "files": generated_files,
            "warnings": warnings,
        }
    )
