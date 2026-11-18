# Keeps Luna Lumia's PC lights reachable: the iCUE bridge and OpenRGB's SDK server.
# install.ps1 copies this next to the bridge and starts it at sign-in, hidden.
# Every 30 seconds it starts whichever of them is not listening, so nothing needs a reboot.

param(
    [string]$InstallDir = $PSScriptRoot,
    [int]$IntervalSeconds = 30
)

$ErrorActionPreference = "Continue"
$Settings = Get-Content (Join-Path $InstallDir "lumia_keeper.json") -Raw | ConvertFrom-Json
$Log = Join-Path $InstallDir "lumia_keeper.log"
# A start that keeps failing logs every minute, so begin afresh past 1 MB.
if ((Test-Path $Log) -and (Get-Item $Log).Length -gt 1MB) { Remove-Item $Log }

function Write-Log($Message) {
    "$(Get-Date -Format s) $Message" | Add-Content -Path $Log -Encoding utf8
}

function Test-Listening([int]$Port) {
    [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Start-Bridge {
    $python = Join-Path $InstallDir "python\pythonw.exe"
    $launch = "-c `"import sys; sys.path.insert(0, r'$InstallDir'); import icue_bridge; icue_bridge.main()`""
    Start-Process $python -ArgumentList $launch -WorkingDirectory $InstallDir
    Write-Log "Started the iCUE bridge."
}

function Start-OpenRGB {
    $exe = $Settings.openrgb_path
    # OpenRGB opened without --server never starts its server, so restart it with one.
    $running = Get-Process OpenRGB -ErrorAction SilentlyContinue
    if ($running) {
        $running | Stop-Process -Force
        Start-Sleep -Seconds 2
        Write-Log "OpenRGB was running without its server, so it was restarted with it."
    }
    Start-Process $exe -ArgumentList "--server", "--startminimized" -WorkingDirectory (Split-Path $exe)
    Write-Log "Started OpenRGB's server."
}

# A program can take a few seconds to open its port, so act only after two silent checks.
# The bridge has nothing else starting it, so it starts on the first one.
$silent = @{ bridge = 1; openrgb = 0 }
Write-Log "Keeper started."
while ($true) {
    $checks = @{ bridge = $Settings.bridge_port }
    if ($Settings.openrgb_path -and (Test-Path $Settings.openrgb_path)) { $checks.openrgb = $Settings.openrgb_port }
    foreach ($name in @($checks.Keys)) {
        if (Test-Listening $checks[$name]) {
            $silent[$name] = 0
            continue
        }
        $silent[$name] += 1
        if ($silent[$name] -lt 2) { continue }
        try {
            if ($name -eq "bridge") { Start-Bridge } else { Start-OpenRGB }
        } catch {
            Write-Log "Could not start ${name}: $_"
        }
        $silent[$name] = 0
    }
    Start-Sleep -Seconds $IntervalSeconds
}
