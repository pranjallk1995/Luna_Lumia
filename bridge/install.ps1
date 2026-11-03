# Install Luna Lumia's iCUE bridge on this Windows PC. See "PC RGB lights" in the README.
# Keeps its own Python in -InstallDir, so nothing is installed system-wide.

param(
    [string]$InstallDir = "$env:LOCALAPPDATA\LunaLumia\icue-bridge",
    [int]$Port = 6743,
    [string[]]$DeviceTypes = @("keyboard", "mouse"),
    [string[]]$AllowFrom = @("LocalSubnet"),
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
$Shortcut = Join-Path ([Environment]::GetFolderPath("Startup")) "Luna Lumia iCUE bridge.lnk"
$Utf8NoBom = New-Object Text.UTF8Encoding($false)

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Stop-Bridge {
    Get-Process pythonw, python -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($InstallDir, [StringComparison]::OrdinalIgnoreCase) } |
        Stop-Process -Force
}

function Get-Verified($Url, $Sha256, $Path) {
    Invoke-WebRequest -Uri $Url -OutFile $Path -UseBasicParsing
    if ((Get-FileHash $Path -Algorithm SHA256).Hash -ne $Sha256.ToUpper()) {
        throw "Download failed verification: $Url"
    }
}

if ($Uninstall) {
    Stop-Bridge
    Remove-Item $Shortcut -ErrorAction SilentlyContinue
    if (Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue) {
        if (Test-Admin) {
            Remove-NetFirewallRule -DisplayName $RuleName
        } else {
            Write-Host "Run this as admin to remove the firewall rule: Remove-NetFirewallRule -DisplayName '$RuleName'"
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

Copy-Item (Join-Path $PSScriptRoot "icue_bridge.py") $InstallDir -Force

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

$PythonW = Join-Path $Python "pythonw.exe"
$Launch = "-c `"import sys; sys.path.insert(0, r'$InstallDir'); import icue_bridge; icue_bridge.main()`""

if (-not $NoStartup) {
    $link = (New-Object -ComObject WScript.Shell).CreateShortcut($Shortcut)
    $link.TargetPath = $PythonW
    $link.Arguments = $Launch
    $link.WorkingDirectory = $InstallDir
    $link.Save()
}

if (-not $NoFirewall) {
    $firewall = "New-NetFirewallRule -DisplayName '$RuleName' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -RemoteAddress $($AllowFrom -join ',') -Profile Any"
    if (Test-Admin) {
        Remove-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
        Invoke-Expression $firewall | Out-Null
    } else {
        Write-Host "Not running as admin, so the firewall was not changed. From an admin PowerShell, run:"
        Write-Host "  $firewall"
    }
}

if (-not $NoStart) {
    Start-Process $PythonW -ArgumentList $Launch -WorkingDirectory $InstallDir
    Start-Sleep -Seconds 3
    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
        Write-Host "The bridge is listening on port $Port."
    } else {
        Write-Host "The bridge did not start. Check $InstallDir\icue_bridge.log"
    }
}

$address = (Get-NetIPConfiguration | Where-Object IPv4DefaultGateway | Select-Object -First 1).IPv4Address.IPAddress
Write-Host ""
Write-Host "Add this PC to LUNALUMIA_ICUE_TOKENS in Lumia's .env, then restart Lumia:"
Write-Host "  $address=$(Get-Content $TokenFile -Raw)"
