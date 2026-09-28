<#
.SYNOPSIS
    Patches a Python embeddable distribution's ._pth file so it behaves like a
    normal installation: pip-installed packages become importable, and the
    project root (one level up from the embeddable runtime folder) is added
    to sys.path so this app's own "app" package can be found.
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$PthPath
)

$lines = Get-Content -LiteralPath $PthPath
$output = New-Object System.Collections.Generic.List[string]

foreach ($line in $lines) {
    if ($line -match '^\s*#\s*import site\s*$') {
        # Uncomment "import site" so pip-installed packages under
        # Lib\site-packages are importable.
        $output.Add('import site')
    }
    elseif ($line.Trim() -eq '.') {
        $output.Add($line)
        # Add the project root (parent of the embeddable runtime folder).
        $output.Add('..')
    }
    else {
        $output.Add($line)
    }
}

Set-Content -LiteralPath $PthPath -Value $output
