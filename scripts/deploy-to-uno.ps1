[CmdletBinding()]
param(
    [string]$Target = "arduino@alfred.local",
    [string]$FallbackAddress = "192.168.1.41",
    [string]$RemoteHome = "/home/arduino",
    [switch]$Reboot,
    [switch]$SkipReboot
)

$ErrorActionPreference = "Stop"
# Windows PowerShell otherwise prefixes text piped to native SSH with a BOM.
# Bash treats that invisible marker as part of the first command name.
$OutputEncoding = [Text.UTF8Encoding]::new($false)
if ($Reboot -and $SkipReboot) {
    throw "Choose either -Reboot or -SkipReboot, not both."
}
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ProjectName = Split-Path $ProjectRoot -Leaf
$ArchiveName = "alfred-deploy-$([DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')).tar.gz"
$LocalArchive = Join-Path ([IO.Path]::GetTempPath()) $ArchiveName
$RemoteArchive = "$RemoteHome/$ArchiveName"
$SshOptions = @("-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=15")
$DeployKey = Join-Path $env:USERPROFILE ".ssh\alfred_uno_ed25519"
if (Test-Path -LiteralPath $DeployKey) {
    $SshOptions += @("-i", $DeployKey, "-o", "IdentitiesOnly=yes")
}

function Test-TcpPort([string]$HostName, [int]$Port = 22, [int]$TimeoutMs = 3000) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $connection = $client.ConnectAsync($HostName, $Port)
        if (-not $connection.Wait($TimeoutMs)) {
            return $false
        }
        return $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

$TargetParts = $Target -split "@", 2
if ($TargetParts.Count -ne 2) {
    throw "Target must use the form user@host."
}
$TargetUser = $TargetParts[0]
$TargetHost = $TargetParts[1]
if (-not (Test-TcpPort $TargetHost)) {
    if ($TargetHost.EndsWith(".local") -and (Test-TcpPort $FallbackAddress)) {
        $Target = "${TargetUser}@${FallbackAddress}"
        Write-Warning "Could not resolve or reach $TargetHost; using the UNO's fallback address $FallbackAddress."
    }
    else {
        throw "Cannot reach $TargetHost on SSH port 22. Confirm that the UNO and this PC are on the same Wi-Fi."
    }
}
else {
    Write-Host "Found the UNO at $TargetHost." -ForegroundColor DarkGray
}

$RemoteTokenLine = Get-Content (Join-Path $ProjectRoot ".env") |
    Where-Object { $_ -match '^TV_REMOTE_TOKEN=' } |
    Select-Object -First 1
if (-not $RemoteTokenLine) {
    throw "TV_REMOTE_TOKEN is missing from .env. Add a private 12+ character value before deployment."
}
$RemoteToken = ($RemoteTokenLine -split '=', 2)[1].Trim()
if ($RemoteToken -notmatch '^[A-Za-z0-9_-]{12,64}$') {
    throw "TV_REMOTE_TOKEN must contain 12-64 letters, numbers, underscores, or hyphens."
}
$TtsVoiceLine = Get-Content (Join-Path $ProjectRoot ".env") |
    Where-Object { $_ -match '^ALFRED_TTS_VOICE=' } |
    Select-Object -First 1
$TtsVoice = if ($TtsVoiceLine) { ($TtsVoiceLine -split '=', 2)[1].Trim() } else { "en-GB-RyanNeural" }
if ($TtsVoice -notmatch '^[A-Za-z0-9:-]{4,80}$') {
    throw "ALFRED_TTS_VOICE contains unsupported characters."
}
$RemoteSettings = "ALFRED_HOST=0.0.0.0`nDASHBOARD_TIME_ZONE=America/Chicago`nTV_REMOTE_TOKEN=$RemoteToken`nSTEPS_CACHE_SECONDS=120`nHEART_RATE_CACHE_SECONDS=120`nWEATHER_CACHE_SECONDS=600`nALFRED_PIPER_MODEL=data/voices/en_GB-semaine-medium.onnx`nALFRED_PIPER_SPEAKER=2`nALFRED_TTS_VOICE=$TtsVoice`nALFRED_TTS_RATE=+5%`nALFRED_TTS_VOLUME=+0%`nALFRED_TTS_PITCH=+0Hz`nALFRED_VOICE_INPUT_ENABLED=true`nALFRED_WAKE_WORD=Alfred`nALFRED_WAKE_WORDS=Alfred,Computer,Jarvis`nALFRED_WAKE_ALIASES=Alfred,Alford,Fred,Computer,Jarvis,Jervis`nALFRED_VOICE_SAMPLE_RATE=16000`nALFRED_VOSK_MODEL=data/voices/vosk-model-small-en-us-0.15`n"
$RemoteSettingsBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($RemoteSettings))

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found. Install the Windows OpenSSH Client and retry."
    }
}

function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Program exited with code $LASTEXITCODE."
    }
}

function Invoke-RemoteBash([string]$Script, [string]$BashArguments) {
    # Passing a here-string through Windows PowerShell's native pipeline can
    # prepend a UTF-8 BOM. Transfer the script as base64 so bash always sees
    # the exact first command, regardless of the host PowerShell version.
    $scriptBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Script))
    $remoteOutput = & ssh @SshOptions $Target "printf '%s' '$scriptBase64' | base64 -d | bash -s -- $BashArguments"
    $remoteExitCode = $LASTEXITCODE
    if ($null -ne $remoteOutput) {
        $remoteOutput | ForEach-Object { Write-Host $_ }
    }
    return [int]$remoteExitCode
}

Require-Command "tar"
Require-Command "ssh"
Require-Command "scp"

Write-Host "Packaging Alfred..." -ForegroundColor Cyan
try {
    Push-Location (Split-Path $ProjectRoot -Parent)
    $tarArguments = @(
        "-czf", $LocalArchive,
        "--exclude=$ProjectName/.venv*",
        "--exclude=$ProjectName/node_modules",
        "--exclude=$ProjectName/frontend/node_modules",
        "--exclude=$ProjectName/android-companion/.gradle",
        "--exclude=$ProjectName/android-companion/build",
        "--exclude=$ProjectName/android-companion/app/build",
        "--exclude=$ProjectName/data/secrets",
        "--exclude=$ProjectName/data/cache",
        "--exclude=$ProjectName/data/logs",
        "--exclude=$ProjectName/data/voices",
        "--exclude=$ProjectName/.env",
        "--exclude=$ProjectName/.git",
        "--exclude=$ProjectName/__pycache__",
        $ProjectName
    )
    Invoke-Checked "tar" $tarArguments
}
finally {
    Pop-Location
}

try {
    Write-Host "Uploading to $Target..." -ForegroundColor Cyan
    Invoke-Checked "scp" (@($SshOptions) + @($LocalArchive, "${Target}:$RemoteArchive"))

    $remoteScript = @'
set -Eeuo pipefail

archive="$1"
remote_home="$2"
remote_settings_b64="$3"
project_dir="$remote_home/Alfred"
staging_dir="$(mktemp -d "$remote_home/.alfred-deploy.XXXXXX")"

cleanup() {
  rm -f -- "$archive"
  rm -rf -- "$staging_dir"
}
trap cleanup EXIT

tar -xzf "$archive" -C "$staging_dir"
incoming="$staging_dir/Alfred"

for required in app.py requirements.txt start-dashboard.sh; do
  if [[ ! -f "$incoming/$required" ]]; then
    echo "Deployment archive is missing $required" >&2
    exit 1
  fi
done

if [[ ! -f "$project_dir/.env" || ! -d "$project_dir/data/secrets" ]]; then
  echo "The UNO installation is missing .env or data/secrets; refusing to overwrite it." >&2
  exit 1
fi

cp -a "$incoming/." "$project_dir/"
chmod +x "$project_dir/start-dashboard.sh" "$project_dir/install-kiosk-autostart.sh" "$project_dir/scripts/configure-tv-display.sh" "$project_dir/scripts/configure-tv-audio.sh" "$project_dir/scripts/check-microphone.sh"

settings_update="$staging_dir/remote-settings.env"
printf '%s' "$remote_settings_b64" | base64 --decode > "$settings_update"
python3 "$project_dir/scripts/merge-env.py" "$project_dir/.env" "$settings_update"

if [[ ! -x "$project_dir/.venv/bin/python" ]]; then
  python3 -m venv "$project_dir/.venv"
fi

"$project_dir/.venv/bin/python" -m pip install --disable-pip-version-check -q -r "$project_dir/requirements.txt"

voice_dir="$project_dir/data/voices"
voice_model="$voice_dir/en_GB-semaine-medium.onnx"
voice_config="$voice_model.json"
if [[ ! -s "$voice_model" || ! -s "$voice_config" ]]; then
  echo "Downloading Alfred's deeper British neural voice (one-time, about 77 MB)..."
  mkdir -p "$voice_dir"
  "$project_dir/.venv/bin/python" -m piper.download_voices \
    --data-dir "$voice_dir" en_GB-semaine-medium
fi

vosk_model_dir="$voice_dir/vosk-model-small-en-us-0.15"
if [[ ! -s "$vosk_model_dir/am/final.mdl" ]]; then
  echo "Downloading Alfred's offline wake-word model (one-time, about 40 MB)..."
  vosk_archive="$staging_dir/vosk-model-small-en-us-0.15.zip"
  wget --quiet --output-document="$vosk_archive" \
    'https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip'
  unzip -q -o "$vosk_archive" -d "$voice_dir"
fi
if [[ ! -s "$vosk_model_dir/am/final.mdl" ]]; then
  echo "The downloaded Vosk model is incomplete." >&2
  exit 1
fi

echo "Alfred deployed successfully."
'@

    Write-Host "Installing the update and checking dependencies..." -ForegroundColor Cyan
    $remoteExitCode = Invoke-RemoteBash $remoteScript "'$RemoteArchive' '$RemoteHome' '$RemoteSettingsBase64'"
    if ($remoteExitCode -ne 0) {
        throw "The UNO rejected the deployment."
    }

    if ($Reboot) {
        Write-Host "Rebooting the UNO into the updated dashboard..." -ForegroundColor Cyan
        & ssh @SshOptions -t $Target "sudo /usr/bin/systemctl reboot"
        if ($LASTEXITCODE -ne 0) {
            throw "The deployment completed, but the UNO could not reboot."
        }
        Write-Host "Done. The UNO is rebooting into the updated Alfred dashboard." -ForegroundColor Green
    }
    else {
        # A full UNO reboot can make the Qualcomm HDMI audio card disappear if
        # the television is not ready during kernel probing. Restart only the
        # Alfred process, then ask the existing kiosk to reload its assets.
        $restartScript = @'
set -Eeuo pipefail

project_dir="$1"
remote_token="$2"
ready_url="http://127.0.0.1:8080/healthz"
main_pid="$(systemctl show -p MainPID --value alfred.service 2>/dev/null || true)"

if [[ ! "$main_pid" =~ ^[0-9]+$ ]] || (( main_pid <= 1 )); then
  echo "Alfred files are installed. The backend service is not installed yet; the fresh-image restore installer will create it."
  exit 0
fi

kill "$main_pid"
for _ in {1..40}; do
  if ! kill -0 "$main_pid" 2>/dev/null; then
    break
  fi
  sleep 0.25
done

for _ in {1..80}; do
  if curl --fail --silent "$ready_url" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

if ! curl --fail --silent "$ready_url" >/dev/null; then
  echo "Alfred did not become healthy after deployment." >&2
  exit 1
fi

# Pin HDMI before the kiosk reload creates Chromium's persistent audio stream.
"$project_dir/scripts/configure-tv-audio.sh" || true

curl --fail --silent --request POST \
  --header 'X-Alfred-Remote: 1' \
  --header "X-Alfred-Remote-Token: $remote_token" \
  --header 'Content-Type: application/json' \
  --data '{}' \
  'http://127.0.0.1:8080/api/display/refresh' >/dev/null

echo "Alfred restarted and the kiosk refresh was requested without rebooting Linux."
'@

        Write-Host "Restarting Alfred without rebooting the UNO..." -ForegroundColor Cyan
        $restartExitCode = Invoke-RemoteBash $restartScript "'$RemoteHome/Alfred' '$RemoteToken'"
        if ($restartExitCode -ne 0) {
            throw "The files were deployed, but Alfred could not restart cleanly."
        }
        Write-Host "Done. Alfred was updated without disturbing the HDMI audio device." -ForegroundColor Green
    }
}
finally {
    Remove-Item -LiteralPath $LocalArchive -Force -ErrorAction SilentlyContinue
}
