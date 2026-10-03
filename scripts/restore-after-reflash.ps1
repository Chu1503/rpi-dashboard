[CmdletBinding()]
param(
    [string]$Target = "arduino@alfred.local",
    [string]$FallbackAddress = "192.168.1.41",
    [string]$BackupDirectory = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$KeyPath = Join-Path $env:USERPROFILE ".ssh\alfred_uno_ed25519"

if (-not $BackupDirectory) {
    $backupRoot = Join-Path $env:USERPROFILE "Documents\Alfred-UNO-Backups"
    $latest = Get-ChildItem -LiteralPath $backupRoot -Directory -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latest) { $BackupDirectory = $latest.FullName }
}

$credentialRoot = if ($BackupDirectory) { Join-Path $BackupDirectory "Alfred" } else { $ProjectRoot }
$environmentFile = Join-Path $credentialRoot ".env"
$secretsDirectory = Join-Path $credentialRoot "data\secrets"
if (-not (Test-Path -LiteralPath $environmentFile) -or
    -not (Test-Path -LiteralPath (Join-Path $secretsDirectory "client_secret.json"))) {
    throw "The Alfred credential backup is incomplete. Expected .env and data\secrets under $credentialRoot"
}

Write-Host "Installing the existing Windows SSH key on the fresh UNO." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "setup-uno-ssh-key.ps1") -Target $Target
if ($LASTEXITCODE -ne 0) { throw "SSH key setup failed." }

$sshOptions = @("-i", $KeyPath, "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=8")
& ssh @sshOptions $Target "mkdir -p /home/arduino/Alfred/data/secrets && chmod 700 /home/arduino/Alfred/data/secrets"
if ($LASTEXITCODE -ne 0) { throw "Could not prepare Alfred's credential directory." }

Write-Host "Restoring Alfred's private environment and Google credentials." -ForegroundColor Cyan
& scp @sshOptions $environmentFile "${Target}:/home/arduino/Alfred/.env"
if ($LASTEXITCODE -ne 0) { throw "Could not restore .env." }
Get-ChildItem -LiteralPath $secretsDirectory -File -Filter "*.json" | ForEach-Object {
    & scp @sshOptions $_.FullName "${Target}:/home/arduino/Alfred/data/secrets/$($_.Name)"
    if ($LASTEXITCODE -ne 0) { throw "Could not restore $($_.Name)." }
}
& ssh @sshOptions $Target "chmod 600 /home/arduino/Alfred/.env /home/arduino/Alfred/data/secrets/*.json"
if ($LASTEXITCODE -ne 0) { throw "Could not secure restored credentials." }

Write-Host "Deploying the latest Alfred application." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "deploy-to-uno.ps1") -Target $Target -FallbackAddress $FallbackAddress
if ($LASTEXITCODE -ne 0) { throw "Alfred deployment failed." }

Write-Host "Enter the UNO password once to install the permanent service and kiosk configuration." -ForegroundColor Yellow
& ssh @sshOptions -t $Target "sudo /home/arduino/Alfred/scripts/install-after-reflash.sh"
if ($LASTEXITCODE -ne 0) { throw "Post-flash system installation failed." }

$health = & ssh @sshOptions $Target "curl -fsS http://127.0.0.1:8080/healthz"
if ($LASTEXITCODE -ne 0) { throw "Alfred is installed but its health check failed." }
Write-Host "Restore complete: $health" -ForegroundColor Green
Write-Host "If tv_power is unavailable, re-upload hardware\alfred_ir\alfred_ir.ino from Arduino IDE." -ForegroundColor Yellow
