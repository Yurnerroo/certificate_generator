<#
.SYNOPSIS
    Sets up (if needed) and starts the Certificate Generator locally.

    This is a PowerShell equivalent of run.bat, provided as a fallback for
    machines where double-clicking a .bat file is blocked or silently
    fails (some antivirus/endpoint-security products intercept .bat/.cmd
    script execution). If run.bat doesn't work for you, right-click this
    file and choose "Run with PowerShell", or open PowerShell and run:
        powershell -ExecutionPolicy Bypass -File run.ps1
#>

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$VenvDir = ".venv"
$EmbedDir = ".pyembed"
$PyVersion = "3.12.7"
$Python = $null

function Test-Command($exe, $arguments) {
    try {
        & $exe @arguments *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

# --- Look for an existing system Python first ---
$systemPyExe = $null
$systemPyPrefixArgs = @()
if (Test-Command "py" @("-3", "--version")) {
    $systemPyExe = "py"
    $systemPyPrefixArgs = @("-3")
} elseif (Test-Command "python" @("--version")) {
    $systemPyExe = "python"
    $systemPyPrefixArgs = @()
}

if ($systemPyExe) {
    if (-not (Test-Path "$VenvDir\Scripts\python.exe")) {
        Write-Host "Creating virtual environment..."
        & $systemPyExe @systemPyPrefixArgs -m venv $VenvDir
        if ($LASTEXITCODE -ne 0) {
            Write-Host ""
            Write-Host "Failed to create the virtual environment (see error above)."
            Read-Host "Press Enter to close"
            exit 1
        }
    }
    $Python = "$VenvDir\Scripts\python.exe"
} else {
    # --- No system Python found: download a private, portable copy. ---
    #     No admin rights or installer needed; it lives entirely inside
    #     this project folder (.pyembed) and is not put on the system PATH.
    $Python = "$EmbedDir\python.exe"
    if (-not (Test-Path $Python)) {
        Write-Host "No Python installation was found on this computer."
        Write-Host "Downloading a portable Python $PyVersion runtime just for this app (~11 MB, one-time)..."
        if (-not (Test-Path $EmbedDir)) { New-Item -ItemType Directory -Path $EmbedDir | Out-Null }

        $zipUrl = "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip"
        $zipPath = "$EmbedDir\python-embed.zip"

        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath
        } catch {
            Write-Host ""
            Write-Host "Could not download Python automatically (no internet access?)."
            Write-Host "Please install Python 3.9+ manually from https://www.python.org/downloads/"
            Write-Host "and run this script again."
            Read-Host "Press Enter to close"
            exit 1
        }

        Write-Host "Extracting portable Python..."
        Expand-Archive -Path $zipPath -DestinationPath $EmbedDir -Force
        Remove-Item $zipPath -ErrorAction SilentlyContinue

        # Enable "import site" (so pip-installed packages under Lib\site-packages
        # are importable) and add the project root to sys.path (so this app's own
        # "app" package can be found, since the embeddable runtime is isolated by
        # default).
        Get-ChildItem "$EmbedDir\python3*._pth" | ForEach-Object {
            & powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\patch_embedded_pth.ps1" -PthPath $_.FullName
        }

        Write-Host "Installing pip into the portable runtime..."
        $getPipPath = "$EmbedDir\get-pip.py"
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPipPath
        & $Python $getPipPath --quiet
        Remove-Item $getPipPath -ErrorAction SilentlyContinue

        Write-Host ""
        Write-Host "Note: the portable runtime does not include tkinter, so the native"
        Write-Host "`"Browse...`" folder dialog will be unavailable - just paste the output"
        Write-Host "folder path into the text field instead."
        Write-Host ""
    }
}

Write-Host "Installing dependencies..."
& $Python -m pip install --quiet --upgrade pip
& $Python -m pip install --quiet -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Dependency installation failed. Re-running with full output so you can see why:"
    Write-Host ""
    & $Python -m pip install -r requirements.txt
    Write-Host ""
    Write-Host "(See the error above. A common cause is no internet access or a blocked/very restrictive network.)"
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host "Starting Certificate Generator at http://127.0.0.1:8000 ..."
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 2
    Start-Process "http://127.0.0.1:8000"
} | Out-Null

& $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
$serverExitCode = $LASTEXITCODE

Write-Host ""
if ($serverExitCode -ne 0) {
    Write-Host "The server stopped with an error (see the messages above)."
    Write-Host "A common cause is another program already using port 8000 - close it and try again."
} else {
    Write-Host "The server has stopped."
}
Read-Host "Press Enter to close"
