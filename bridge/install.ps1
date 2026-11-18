# Install Luna Lumia's iCUE bridge on this Windows PC. See "PC RGB lights" in the README.
# Keeps its own Python in -InstallDir, so nothing is installed system-wide.
# A keeper (lumia_keeper.ps1) starts at sign-in and restarts the bridge, and OpenRGB with
# its server, whenever either stops listening.

param(
    [string]$InstallDir = "$env:LOCALAPPDATA\LunaLumia\icue-bridge",
    [int]$Port = 6743,
    [string[]]$DeviceTypes = @("keyboard", "mouse"),
    [string[]]$AllowFrom = @("LocalSubnet"),
    [string]$OpenRGBPath = "",
    [int]$OpenRGBPort = 6742,
    [switch]$NoOpenRGB,
    [switch]$NoFirewall,
    [switch]$NoStartup,
    [switch]$NoStart,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$PythonUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
$PythonSha256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
$CueSdkUrl = "https://files.pythonhosted.org/packages/a6/a5/38725e09cfda81a04c60de15381baefa99e6b59c8222d1f667f2c3959ea0/cuesdk-4.0.84-py3-none-any.whl"
$CueSdkSha256 = "b079fa25eb1c0dd0a5618c1be4b586af0620ece697161536387bae01f46f9003"
$RuleName = "Luna Lumia iCUE bridge"
$OpenRGBRuleName = "Luna Lumia OpenRGB server"
$Startup = [Environment]::GetFolderPath("Startup")
# Older installs started the bridge itself at sign-in; the keeper does that now.
$OldShortcut = Join-Path $Startup "Luna Lumia iCUE bridge.lnk"
$Shortcut = Join-Path $Startup "Luna Lumia keeper.lnk"
$Utf8NoBom = New-Object Text.UTF8Encoding($false)

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Stop-Keeper {
    Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*lumia_keeper.ps1*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

function Find-OpenRGB {
    if ($OpenRGBPath) { return $OpenRGBPath }
    $running = Get-Process OpenRGB -ErrorAction SilentlyContinue | Where-Object Path | Select-Object -First 1
    if ($running) { return $running.Path }
    $places = @("$env:ProgramFiles\OpenRGB\OpenRGB.exe", "${env:ProgramFiles(x86)}\OpenRGB\OpenRGB.exe", "$env:LOCALAPPDATA\Programs\OpenRGB\OpenRGB.exe")
    $places | Where-Object { Test-Path $_ } | Select-Object -First 1
}

function Stop-Bridge {
    Stop-Keeper
    # A bridge started from an admin window hides its path from a normal one, so also go by its port.
    $byPath = Get-Process pythonw, python -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($InstallDir, [StringComparison]::OrdinalIgnoreCase) } |
        ForEach-Object { $_.Id }
    $settingsFile = Join-Path $InstallDir "icue_bridge.json"
    $bridgePort = if (Test-Path $settingsFile) { (Get-Content $settingsFile -Raw | ConvertFrom-Json).port } else { $Port }
    $byPort = Get-NetTCPConnection -State Listen -LocalPort $bridgePort -ErrorAction SilentlyContinue |
        Where-Object { (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName -match "^pythonw?$" } |
        ForEach-Object { $_.OwningProcess }
    foreach ($id in @($byPath) + @($byPort) | Where-Object { $_ } | Select-Object -Unique) {
        try {
            Stop-Process -Id $id -Force -ErrorAction Stop
        } catch {
            throw "Could not stop the bridge running as process $id. It was started from an admin window, so run this from one too."
        }
    }
}

function Get-Verified($Url, $Sha256, $Path) {
    Invoke-WebRequest -Uri $Url -OutFile $Path -UseBasicParsing
    if ((Get-FileHash $Path -Algorithm SHA256).Hash -ne $Sha256.ToUpper()) {
        throw "Download failed verification: $Url"
    }
}

if ($Uninstall) {
    Stop-Bridge
    Remove-Item $Shortcut, $OldShortcut -ErrorAction SilentlyContinue
    foreach ($rule in $RuleName, $OpenRGBRuleName) {
        if (Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue) {
            if (Test-Admin) {
                Remove-NetFirewallRule -DisplayName $rule
            } else {
                Write-Host "Run this as admin to remove the firewall rule: Remove-NetFirewallRule -DisplayName '$rule'"
            }
        }
    }
    Remove-Item $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Removed the bridge. iCUE's own lighting is back."
    return
}

if ($Port -lt 1 -or $Port -gt 65535) { throw "-Port must be from 1 to 65535" }
# Run with -File, PowerShell hands "a,b" over as one string.
$DeviceTypes = @($DeviceTypes -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$AllowFrom = @($AllowFrom -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$Python = Join-Path $InstallDir "python"
$Downloads = Join-Path $env:TEMP "luna-lumia-icue-$PID"
Stop-Bridge
New-Item -ItemType Directory -Force -Path $Python, $Downloads | Out-Null
try {
    if (-not (Test-Path (Join-Path $Python "cuesdk\bin\iCUESDK.x64_2019.dll"))) {
        Write-Host "Downloading Python and Corsair's cuesdk..."
        $pythonZip = Join-Path $Downloads "python.zip"
        $cueZip = Join-Path $Downloads "cuesdk.zip"
        Get-Verified $PythonUrl $PythonSha256 $pythonZip
        Get-Verified $CueSdkUrl $CueSdkSha256 $cueZip
        Expand-Archive $pythonZip -DestinationPath $Python -Force
        Expand-Archive $cueZip -DestinationPath (Join-Path $Downloads "cuesdk") -Force
        Copy-Item (Join-Path $Downloads "cuesdk\cuesdk") $Python -Recurse -Force
    }
} finally {
    Remove-Item $Downloads -Recurse -Force -ErrorAction SilentlyContinue
}

Copy-Item (Join-Path $PSScriptRoot "icue_bridge.py"), (Join-Path $PSScriptRoot "lumia_keeper.ps1") $InstallDir -Force
$OpenRGB = if ($NoOpenRGB) { $null } else { Find-OpenRGB }
if (-not $NoOpenRGB -and -not $OpenRGB) {
    Write-Host "OpenRGB was not found, so the keeper looks after the bridge only. Pass -OpenRGBPath to add it."
}
$keeperSettings = @{ bridge_port = $Port; openrgb_path = $OpenRGB; openrgb_port = $OpenRGBPort } | ConvertTo-Json -Compress
[IO.File]::WriteAllText((Join-Path $InstallDir "lumia_keeper.json"), $keeperSettings, $Utf8NoBom)

# The bridge reads these back; a BOM would break both.
$settings = @{ bind = "0.0.0.0"; port = $Port; device_types = @($DeviceTypes) } | ConvertTo-Json -Compress
[IO.File]::WriteAllText((Join-Path $InstallDir "icue_bridge.json"), $settings, $Utf8NoBom)
$TokenFile = Join-Path $InstallDir "icue_token.txt"
if (-not (Test-Path $TokenFile)) {
    $bytes = New-Object byte[] 40
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $token = [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
    [IO.File]::WriteAllText($TokenFile, $token, $Utf8NoBom)
}

# The bridge has no window once running, so a bad setting has to fail here.
$check = "import sys, pathlib; sys.path.insert(0, r'$InstallDir'); import icue_bridge; icue_bridge.BridgeConfig.load(pathlib.Path(r'$InstallDir') / 'icue_bridge.json')"
& (Join-Path $Python "python.exe") -c $check
if ($LASTEXITCODE -ne 0) { throw "Those settings are not valid, see the error above." }

$Keeper = Join-Path $InstallDir "lumia_keeper.ps1"
$PowerShell = Join-Path $PSHOME "powershell.exe"
$KeeperArgs = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Keeper`""

Remove-Item $OldShortcut -ErrorAction SilentlyContinue
if (-not $NoStartup) {
    $link = (New-Object -ComObject WScript.Shell).CreateShortcut($Shortcut)
    $link.TargetPath = $PowerShell
    $link.Arguments = $KeeperArgs
    $link.WorkingDirectory = $InstallDir
    $link.WindowStyle = 7
    $link.Save()
}

if (-not $NoFirewall) {
    $rules = @{ $RuleName = $Port }
    if ($OpenRGB) { $rules[$OpenRGBRuleName] = $OpenRGBPort }
    foreach ($rule in $rules.Keys) {
        $firewall = "New-NetFirewallRule -DisplayName '$rule' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $($rules[$rule]) -RemoteAddress $($AllowFrom -join ',') -Profile Any"
        if (Test-Admin) {
            Remove-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue
            Invoke-Expression $firewall | Out-Null
        } else {
            Write-Host "Not running as admin, so the firewall was not changed. From an admin PowerShell, run:"
            Write-Host "  $firewall"
        }
    }
}

if (-not $NoStart) {
    # The keeper starts the bridge at once, and OpenRGB's server within a minute.
    Start-Process $PowerShell -ArgumentList $KeeperArgs -WorkingDirectory $InstallDir -WindowStyle Hidden
    Start-Sleep -Seconds 6
    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
        Write-Host "The bridge is listening on port $Port."
    } else {
        Write-Host "The bridge did not start. Check $InstallDir\icue_bridge.log and lumia_keeper.log"
    }
    if ($OpenRGB) { Write-Host "The keeper starts OpenRGB's server within a minute if it is not running." }
}

$address = (Get-NetIPConfiguration | Where-Object IPv4DefaultGateway | Select-Object -First 1).IPv4Address.IPAddress
Write-Host ""
Write-Host "Add this PC to LUNALUMIA_ICUE_TOKENS in Lumia's .env, then restart Lumia:"
Write-Host "  $address=$(Get-Content $TokenFile -Raw)"
