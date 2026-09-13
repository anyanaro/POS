$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$environmentFile = Join-Path $projectRoot ".env.live"

if (-not (Test-Path $environmentFile)) {
    throw "Missing $environmentFile. Copy .env.live.example, supply the PostgreSQL credentials, and rerun."
}

Get-Content $environmentFile | ForEach-Object {
    if ($_ -match '^\s*([^#=\s]+)\s*=\s*(.*)\s*$') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
}

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

Set-Location $projectRoot
& $python scripts\create_live_database.py "POS Live"
& $python manage.py migrate --noinput
& $python manage.py collectstatic --noinput