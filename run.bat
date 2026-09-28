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
rem NOTE: "py"/"python" must be invoked with "call". Some Python version
rem managers (e.g. pyenv-win) put a .bat/.cmd "shim" file on PATH instead of
rem a real .exe. Running a .bat from inside another .bat WITHOUT "call"
rem permanently hands control to that nested script and never returns here -
rem the console would just close after it finishes, with no error shown.
call py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "SYSTEM_PY=py -3"
    goto :try_system
)
call python --version >nul 2>&1
if not errorlevel 1 (
    set "SYSTEM_PY=python"
    goto :try_system
)
goto :bootstrap_embedded

:try_system
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Creating virtual environment...
    call %SYSTEM_PY% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo.
        echo Could not create a virtual environment with your installed Python.
        echo Falling back to a bundled, known-compatible Python runtime instead...
        echo.
        rmdir /s /q "%VENV_DIR%" >nul 2>&1
        goto :bootstrap_embedded
    )
)
set "PYTHON=%VENV_DIR%\Scripts\python.exe"

echo Installing dependencies...
"%PYTHON%" -m pip install --quiet --upgrade pip
"%PYTHON%" -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo.
    echo Installing dependencies failed with your installed Python version.
    echo This is often caused by pip needing to compile a package from source
    echo ^(shown above as red "Building wheel for X ... error" messages^) because
    echo no ready-made package exists for your specific Python version - not
    echo something wrong with your computer.
    echo Falling back to a bundled Python runtime that is known to work well
    echo with this app...
    echo.
    rmdir /s /q "%VENV_DIR%" >nul 2>&1
    goto :bootstrap_embedded
)
goto :run_server

:bootstrap_embedded
rem --- Use (and if needed, download) a private, portable copy of Python. ---
rem     No admin rights or installer needed; it lives entirely inside
rem     this project folder (.pyembed) and is not put on the system PATH.
set "PYTHON=%EMBED_DIR%\python.exe"
if exist "%PYTHON%" goto :install_embedded_deps

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

:install_embedded_deps
echo Installing dependencies...
"%PYTHON%" -m pip install --quiet --upgrade pip
"%PYTHON%" -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo.
    echo Dependency installation failed even with the bundled Python runtime.
    echo Re-running with full output so you can see why:
    echo.
    "%PYTHON%" -m pip install -r requirements.txt
    echo.
    echo ^(A common cause is no internet access, or a corporate/school network
    echo that blocks access to pypi.org - ask IT to allow it if that's the case.^)
    pause
    exit /b 1
)
goto :run_server

:run_server
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
