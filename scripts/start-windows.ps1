param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$AlfredRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$PythonPath = Join-Path $AlfredRoot ".venv\Scripts\python.exe"
$RunDirectory = Join-Path $AlfredRoot "data\run"
$LogDirectory = Join-Path $AlfredRoot "data\logs"
$PidFile = Join-Path $RunDirectory "alfred-windows.pid"

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Missing $PythonPath. Create Alfred's virtual environment and install requirements first."
}

Set-Location -LiteralPath $AlfredRoot
$ConfiguredPort = & $PythonPath -c "from config import settings; print(settings.port)"
$ConfiguredHost = & $PythonPath -c "from config import settings; print(settings.host)"
$AlfredPort = 0
if ($LASTEXITCODE -ne 0 -or -not [int]::TryParse(($ConfiguredPort | Select-Object -Last 1), [ref]$AlfredPort)) {
    throw "Could not read ALFRED_PORT from Alfred's configuration."
}
$AlfredHost = ($ConfiguredHost | Select-Object -Last 1).Trim()
if (-not $AlfredHost) {
    throw "Could not read ALFRED_HOST from Alfred's configuration."
}
$AlfredUrl = "http://127.0.0.1:$AlfredPort/"
$HealthUrl = "${AlfredUrl}healthz"

function Test-AlfredHealth {
    try {
        $Response = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 2
        return $Response.status -eq "ok"
    }
    catch {
        return $false
    }
}

New-Item -ItemType Directory -Path $RunDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null

if (Test-AlfredHealth) {
    Write-Host "Alfred is already running at $AlfredUrl"
}
else {
    if (Test-Path -LiteralPath $PidFile) {
        Remove-Item -LiteralPath $PidFile -Force
    }

    $StandardLog = Join-Path $LogDirectory "alfred-windows.log"
    $ErrorLog = Join-Path $LogDirectory "alfred-windows-error.log"
    $Arguments = @(
        "-m", "waitress",
        "--listen=${AlfredHost}:$AlfredPort",
        "app:app"
    )
    $ServerProcess = Start-Process `
        -FilePath $PythonPath `
        -ArgumentList $Arguments `
        -WorkingDirectory $AlfredRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $StandardLog `
        -RedirectStandardError $ErrorLog `
        -PassThru

    Set-Content -LiteralPath $PidFile -Value $ServerProcess.Id -Encoding ascii

    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 80; $Attempt++) {
        if (Test-AlfredHealth) {
            $Ready = $true
            break
        }
        if ($ServerProcess.HasExited) {
            break
        }
        Start-Sleep -Milliseconds 250
    }

    if (-not $Ready) {
        if (-not $ServerProcess.HasExited) {
            Stop-Process -Id $ServerProcess.Id -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        throw "Alfred did not become ready. Check $ErrorLog"
    }

    Write-Host "Alfred started at $AlfredUrl"
}

if (-not $NoBrowser) {
    Start-Process $AlfredUrl
}
