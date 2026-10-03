$ErrorActionPreference = "Stop"
$AlfredRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$ExpectedPython = (Join-Path $AlfredRoot ".venv\Scripts\python.exe")
$PidFile = Join-Path $AlfredRoot "data\run\alfred-windows.pid"

if (-not (Test-Path -LiteralPath $PidFile -PathType Leaf)) {
    Write-Host "No Alfred launcher PID file exists. Alfred is already stopped or was started another way."
    exit 0
}

$ServerPidText = (Get-Content -LiteralPath $PidFile -Raw).Trim()
$ServerPid = 0
if (-not [int]::TryParse($ServerPidText, [ref]$ServerPid)) {
    throw "The Alfred PID file is invalid: $PidFile"
}

$ServerProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $ServerPid" -ErrorAction SilentlyContinue
if ($null -eq $ServerProcess) {
    Remove-Item -LiteralPath $PidFile -Force
    Write-Host "Alfred was already stopped; removed its stale PID file."
    exit 0
}

if ($ServerProcess.ExecutablePath -ne $ExpectedPython -or $ServerProcess.CommandLine -notmatch "waitress" -or $ServerProcess.CommandLine -notmatch "app:app") {
    throw "Refusing to stop PID $ServerPid because it is not the Alfred Waitress process."
}

$AllProcesses = Get-CimInstance Win32_Process
$ProcessIds = [System.Collections.Generic.List[int]]::new()
$ProcessIds.Add($ServerPid)
for ($Index = 0; $Index -lt $ProcessIds.Count; $Index++) {
    $ParentId = $ProcessIds[$Index]
    foreach ($Child in $AllProcesses | Where-Object { $_.ParentProcessId -eq $ParentId }) {
        if (-not $ProcessIds.Contains([int]$Child.ProcessId)) {
            $ProcessIds.Add([int]$Child.ProcessId)
        }
    }
}

for ($Index = $ProcessIds.Count - 1; $Index -ge 0; $Index--) {
    Stop-Process -Id $ProcessIds[$Index] -ErrorAction SilentlyContinue
}

Remove-Item -LiteralPath $PidFile -Force
Write-Host "Alfred stopped."
