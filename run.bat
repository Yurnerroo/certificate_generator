@echo off
setlocal
cd /d "%~dp0"

set VENV_DIR=.venv
set PYTHON=%VENV_DIR%\Scripts\python.exe

if not exist "%PYTHON%" (
    echo Creating virtual environment...
    py -3 -m venv "%VENV_DIR%" 2>nul
    if not exist "%PYTHON%" (
        python -m venv "%VENV_DIR%"
    )
)

echo Installing dependencies...
"%PYTHON%" -m pip install --quiet --upgrade pip
"%PYTHON%" -m pip install --quiet -r requirements.txt

echo Starting Certificate Generator at http://127.0.0.1:8000 ...
start "" cmd /c "timeout /t 2 >nul && start "" http://127.0.0.1:8000"
"%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

endlocal
