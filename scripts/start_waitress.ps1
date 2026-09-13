param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("test", "live")]
    [string]$Environment,
    [Parameter(Mandatory = $true)]
    [int]$Port
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$environmentFile = Join-Path $projectRoot ".env.$Environment"

if (-not (Test-Path $environmentFile)) {
    throw "Missing $environmentFile. Copy .env.$Environment.example and set its real values."
}

Get-Content $environmentFile | ForEach-Object {
    if ($_ -match '^\s*([^#=\s]+)\s*=\s*(.*)\s*$') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
}

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe"
}
if (-not (Test-Path $python)) {
    throw "Python interpreter was not found. Install the project virtual environment or update start_waitress.ps1."
}

Set-Location $projectRoot
& $python -m waitress --host=127.0.0.1 --port=$Port --trusted-proxy=127.0.0.1 --trusted-proxy-headers=x-forwarded-proto POS.wsgi:application