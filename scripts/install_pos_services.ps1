param(
    [string]$NssmPath = "C:\nssm\nssm.exe"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $PSScriptRoot "start_waitress.ps1"
$logsDirectory = Join-Path $projectRoot "logs"

New-Item -ItemType Directory -Path $logsDirectory -Force | Out-Null

if (-not (Test-Path $NssmPath)) {
    throw "NSSM was not found at $NssmPath. Download NSSM, then rerun with -NssmPath."
}

foreach ($service in @(
    @{ Name = "POS-Test"; Environment = "test"; Port = 8101 },
    @{ Name = "POS-Live"; Environment = "live"; Port = 8102 }
)) {
    $existing = Get-Service -Name $service.Name -ErrorAction SilentlyContinue
    if (-not $existing) {
        & $NssmPath install $service.Name "powershell.exe" "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`" -Environment $($service.Environment) -Port $($service.Port)"
    }
    & $NssmPath set $service.Name AppDirectory $projectRoot
    & $NssmPath set $service.Name Start SERVICE_AUTO_START
    & $NssmPath set $service.Name AppStdout (Join-Path $projectRoot "logs\$($service.Environment)-waitress.out.log")
    & $NssmPath set $service.Name AppStderr (Join-Path $projectRoot "logs\$($service.Environment)-waitress.err.log")
    if ($existing) {
        & $NssmPath restart $service.Name
    } else {
        & $NssmPath start $service.Name
    }
}