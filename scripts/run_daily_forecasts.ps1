$ErrorActionPreference = "Stop"
Set-Location "D:\ssl\django-projects\POS"

# Use the project virtual environment when present.
$python = "python"
if (Test-Path ".\.venv\Scripts\python.exe") {
    $python = ".\.venv\Scripts\python.exe"
}

& $python manage.py generate_daily_forecasts --horizon 30
if ($LASTEXITCODE -ne 0) {
    throw "Daily forecast generation failed with exit code $LASTEXITCODE"
}
