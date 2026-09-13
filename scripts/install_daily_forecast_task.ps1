$ErrorActionPreference = "Stop"
$projectRoot = "D:\ssl\django-projects\POS"
$runner = Join-Path $projectRoot "scripts\run_daily_forecasts.ps1"
$taskName = "POS Daily Forecast Generation"
$action = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$runner`""

schtasks.exe /Create /TN $taskName /TR $action /SC DAILY /ST 02:00 /F
Write-Host "Created '$taskName' to run daily at 02:00."
