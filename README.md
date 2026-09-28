# Certificate Generator

A local-only web app that generates pixel-perfect PDF certificates for КВАДРАТ ЗДАНЕВИЧА
training courses. It runs entirely on your own machine — there is no cloud deployment,
no external hosting, and (aside from optional auto-translation) no dependency on the
internet.

You fill in a simple Ukrainian-labeled web form (recipient names, course title, location,
month/year), and the app renders one PDF certificate per recipient by compositing your
text onto the real certificate design (`design_assets/certificate_template.png`) at the
exact coordinates and fonts extracted from the original certificate PDF
(`design_assets/layout_spec.json`). Long names/titles are automatically wrapped and, if
still too large, the font size is shrunk until everything fits neatly inside its box.

## Requirements

- Python 3.9+ (Windows, macOS, or Linux) — **not required on Windows**, see below.
- Internet access is only needed for the optional auto-translation of course
  title/location into English — everything else, including transliteration of
  names, works fully offline.

### No Python installed? (Windows)

`run.bat` works even without Python pre-installed: if it can't find a system
Python, it automatically downloads a small (~11 MB), private, portable Python
runtime into a local `.pyembed/` folder — no admin rights, no installer, and
nothing is added to your system PATH. This only happens once; subsequent runs
reuse it. Internet access is required for this one-time download only. The
portable runtime doesn't include `tkinter`, so the "Browse..." folder-picker
dialog isn't available in that mode — just paste the output folder path into
the text field instead.

## Quick start

**Windows**

```
run.bat
```

**macOS / Linux**

```
chmod +x run.sh   # first time only
./run.sh
```

Either script will:

1. Create a local virtual environment (`.venv/`) if one doesn't already exist.
2. Install dependencies from `requirements.txt`.
3. Start the app with `uvicorn` on `http://127.0.0.1:8000`.
4. Open that URL in your default browser automatically.

To stop the server, close the terminal window or press `Ctrl+C`.

### Manual setup (alternative)

```
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000` in your browser.

## Using the form

The form has 7 arguments. Everything else on the certificate (logo, "СЕРТИФІКАТ /
CERTIFICATE" heading, QR code, trainer name/signature, decorative shapes) is fixed and
baked into the template image — it is not editable from the UI.

| # | Field (Ukrainian label) | Description |
|---|--------------------------|-------------|
| 1 | **Імена отримувачів** | Multi-line textarea, one recipient's full name per line (Ukrainian). The number of names entered here determines how many PDF certificates are generated. |
| 2 | **Імена отримувачів (англ.)** | Optional multi-line textarea. If provided, must have the same number of lines as field 1, in the same order. If left blank, each Ukrainian name is automatically transliterated to Latin script using the official Ukrainian national transliteration table (Resolution of the Cabinet of Ministers of Ukraine No. 55, 2010 — the same rules used for passports). |
| 3 | **Назва тренінгу** | Text input, the course/training title in Ukrainian. |
| 4 | **Назва тренінгу (англ.)** | Optional text input. If left blank, it's auto-translated from Ukrainian using a free translation service. If translation fails (e.g. no internet), the field is left blank and a warning is shown — you can fill it in manually and regenerate. |
| 5 | **Локація** | Text input, location in Ukrainian (e.g. `м. Івано-Франківськ, Україна`). |
| 6 | **Локація (англ.)** | Optional text input, same auto-translate-with-fallback behavior as field 4. |
| 7 | **Дата (Місяць, Рік)** | A month dropdown (Ukrainian month names) and a year selector. Together they produce both the Ukrainian date string (e.g. `Липень, 2026`) and the English date string (e.g. `July, 2026`) automatically. |

### Output folder

Use the **"Огляд..."** (Browse) button to open a native OS folder-picker dialog, or type/paste
a path directly into the text field. The last folder you used is remembered between runs
(stored locally in a gitignored `config.json`). The folder is created automatically if it
doesn't exist. After generation, a success summary lists the generated files and lets you
open the output folder directly (Windows only).

Generated filenames are sanitized and numbered, e.g. `01_Ivan_Petrenko.pdf`,
`02_Maruk_Nadiia.pdf`.

## Error handling

The app validates input and reports problems in Ukrainian directly in the UI, including:

- An empty list of recipient names.
- A mismatched number of lines between the Ukrainian and English name lists.
- Translation/transliteration failures (translation falls back to a blank field with a
  warning; transliteration is fully offline and does not fail on network issues).
- An invalid or unwritable output folder.

## Project structure

```
app/
  main.py                     FastAPI app: routes, request validation, orchestration
  config.py                   Persists the last-used output folder to config.json
  services/
    transliteration.py        UA -> Latin transliteration (Resolution No. 55/2010)
    translation.py            UA -> EN auto-translation with graceful fallback
    dates.py                  Ukrainian month names and UA/EN date formatting
    certificate.py            Core rendering engine: layout, wrap+shrink autofit, PDF export
  templates/index.html        Single-page form UI
  static/style.css, app.js    Styling and frontend behavior
design_assets/                 Certificate template, logo, layout spec, fonts, reference PDF
requirements.txt
run.bat / run.sh                Launcher scripts
```

## Design assets

`design_assets/` contains the real certificate background (with only the 4 dynamic text
areas whited out), the standalone logo, the exact box layout/fonts/colors extracted from
the original certificate PDF, and metric-compatible open-source fonts (Arimo, OFL
licensed) used as substitutes for Arial/Arial-Bold. These are treated as fixed design
inputs and are not modified by the app at runtime.