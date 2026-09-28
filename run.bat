@echo off
rem If you are reading this because double-clicking run.bat does nothing or
rem the console flashes and closes instantly, some antivirus/endpoint-security
rem software on your machine may be blocking .bat script execution. Right-click
rem "run.ps1" in this folder and choose "Run with PowerShell" instead - it does
rem exactly the same thing as this script.
setlocal enabledelayedexpansion
cd /d "%~dp0"

set VENV_DIR=.venv
set EMBED_DIR=.pyembed
set PY_VERSION=3.12.7
set PYTHON=

rem --- Look for an existing system Python first ---
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "SYSTEM_PY=py -3"
    goto :found_system
)
python --version >nul 2>&1
if not errorlevel 1 (
    set "SYSTEM_PY=python"
    goto :found_system
)
goto :bootstrap_embedded

:found_system
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Creating virtual environment...
    %SYSTEM_PY% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo.
        echo Failed to create the virtual environment ^(see error above^).
        pause
        exit /b 1
    )
)
set "PYTHON=%VENV_DIR%\Scripts\python.exe"
goto :install_deps

:bootstrap_embedded
rem --- No system Python found: download a private, portable copy. ---
rem     No admin rights or installer needed; it lives entirely inside
rem     this project folder (.pyembed) and is not put on the system PATH.
set "PYTHON=%EMBED_DIR%\python.exe"
if exist "%PYTHON%" goto :install_deps

echo No Python installation was found on this computer.
echo Downloading a portable Python %PY_VERSION% runtime just for this app (~11 MB, one-time)...
if not exist "%EMBED_DIR%" mkdir "%EMBED_DIR%"

set "ZIP_URL=https://www.python.org/ftp/python/%PY_VERSION%/python-%PY_VERSION%-embed-amd64.zip"
set "ZIP_PATH=%EMBED_DIR%\python-embed.zip"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri '%ZIP_URL%' -OutFile '%ZIP_PATH%'"
if errorlevel 1 (
    echo.
    echo Could not download Python automatically ^(no internet access?^).
    echo Please install Python 3.9+ manually from https://www.python.org/downloads/
    echo and run this script again.
    pause
    exit /b 1
)

echo Extracting portable Python...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Expand-Archive -Path '%ZIP_PATH%' -DestinationPath '%EMBED_DIR%' -Force"
del "%ZIP_PATH%" >nul 2>&1

rem Enable "import site" (so pip-installed packages under Lib\site-packages are
rem importable) and add the project root to sys.path (so this app's own
rem "app" package can be found, since the embeddable runtime is isolated by
rem default).
for %%f in ("%EMBED_DIR%\python3*._pth") do (
    powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\patch_embedded_pth.ps1" -PthPath "%%~f"
)

echo Installing pip into the portable runtime...
set "GETPIP_PATH=%EMBED_DIR%\get-pip.py"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%GETPIP_PATH%'"
"%PYTHON%" "%GETPIP_PATH%" --quiet
del "%GETPIP_PATH%" >nul 2>&1

echo.
echo Note: the portable runtime does not include tkinter, so the native
echo "Browse..." folder dialog will be unavailable - just paste the output
echo folder path into the text field instead.
echo.

:install_deps
echo Installing dependencies...
"%PYTHON%" -m pip install --quiet --upgrade pip
"%PYTHON%" -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo.
    echo Dependency installation failed. Re-running with full output so you can see why:
    echo.
    "%PYTHON%" -m pip install -r requirements.txt
    echo.
    echo ^(See the error above. A common cause is no internet access or a blocked/very restrictive network.^)
    pause
    exit /b 1
)

echo Starting Certificate Generator at http://127.0.0.1:8000 ...
start "" cmd /c "timeout /t 2 >nul && start "" http://127.0.0.1:8000"
"%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
if errorlevel 1 (
    echo The server stopped with an error ^(see the messages above^).
    echo A common cause is another program already using port 8000 - close it and try again.
) else (
    echo The server has stopped.
)
pause
endlocal
