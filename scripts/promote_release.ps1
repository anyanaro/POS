param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("test", "live")]
    [string]$Environment
)

$ErrorActionPreference = "Stop"
$releaseRoot = "D:\ssl\django-projects\POS-$Environment"
$serviceName = "POS-" + (Get-Culture).TextInfo.ToTitleCase($Environment)
$python = "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe"

$sourceRoot = if ($Environment -eq "test") {
    "D:\ssl\django-projects\POS"
} else {
    "D:\ssl\django-projects\POS-test"
}

if (-not (Test-Path $releaseRoot)) {
    throw "Release folder does not exist: $releaseRoot"
}
if (-not (Test-Path $sourceRoot)) {
    throw "Release source folder does not exist: $sourceRoot"
}
if (-not (Test-Path $python)) {
    throw "Python interpreter was not found: $python"
}

robocopy $sourceRoot $releaseRoot /MIR /XD .git .venv logs staticfiles media /XF .env.test .env.live
if ($LASTEXITCODE -gt 7) {
    throw "Release copy failed with robocopy exit code $LASTEXITCODE"
}

$environmentFile = Join-Path $releaseRoot ".env.$Environment"
if (-not (Test-Path $environmentFile)) {
    throw "Missing retained environment file: $environmentFile"
}

Get-Content $environmentFile | ForEach-Object {
    if ($_ -match '^\s*([^#=\s]+)\s*=\s*(.*)\s*$') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
}

Push-Location $releaseRoot
try {
    & $python manage.py check
    if ($LASTEXITCODE -ne 0) { throw "Django check failed." }
    & $python manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw "Database migration failed." }
    & $python manage.py collectstatic --noinput
    if ($LASTEXITCODE -ne 0) { throw "Static asset collection failed." }
} finally {
    Pop-Location
}

& "C:\nssm\nssm.exe" restart $serviceName
if ($LASTEXITCODE -ne 0) {
    throw "Could not restart $serviceName"
}

Write-Output "Promoted $sourceRoot to $releaseRoot and restarted $serviceName."