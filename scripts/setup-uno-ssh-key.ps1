param(
    [string]$Target = "arduino@alfred.local"
)

$ErrorActionPreference = "Stop"
$KeyDirectory = Join-Path $env:USERPROFILE ".ssh"
$KeyPath = Join-Path $KeyDirectory "alfred_uno_ed25519"
$PublicKeyPath = "$KeyPath.pub"

foreach ($command in @("ssh", "ssh-keygen")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required command '$command' was not found. Install Windows OpenSSH Client first."
    }
}

New-Item -ItemType Directory -Path $KeyDirectory -Force | Out-Null

if (-not (Test-Path -LiteralPath $KeyPath)) {
    Write-Host "Creating a dedicated Alfred deployment key." -ForegroundColor Cyan
    Write-Host "When asked for a passphrase, press Enter twice to leave it blank." -ForegroundColor Yellow
    & ssh-keygen -t ed25519 -f $KeyPath -C "alfred-uno-deploy"
    if ($LASTEXITCODE -ne 0) {
        throw "ssh-keygen exited with code $LASTEXITCODE."
    }
}

if (-not (Test-Path -LiteralPath $PublicKeyPath)) {
    throw "The public key was not created at $PublicKeyPath."
}

$PublicKeyBase64 = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes((Get-Content -LiteralPath $PublicKeyPath -Raw).Trim() + "`n")
)
$RemoteCommand = "umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; key=`$(printf '%s' '$PublicKeyBase64' | base64 --decode); grep -qxF `"`$key`" ~/.ssh/authorized_keys || printf '%s`n' `"`$key`" >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys"

Write-Host "Enter the UNO password once to install the public key." -ForegroundColor Cyan
& ssh -o ConnectTimeout=8 $Target $RemoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "The UNO rejected the SSH key installation."
}

Write-Host "Verifying passwordless SSH..." -ForegroundColor Cyan
& ssh -o BatchMode=yes -o ConnectTimeout=8 -i $KeyPath -o IdentitiesOnly=yes $Target "true"
if ($LASTEXITCODE -ne 0) {
    throw "The key was copied, but passwordless SSH verification failed."
}
