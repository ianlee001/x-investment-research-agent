param([switch]$Database)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtimePath = Join-Path $projectRoot '.runtime'
$pidPath = Join-Path $runtimePath 'app-processes.json'
function Stop-OwnedProcessTree($ownedProcess) {
    # Windows venv python.exe may launch the base interpreter. Capture and verify descendants
    # while the recorded parent still exists, then stop children first to avoid orphan servers.
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($ownedProcess.Id)" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        $liveChild = Get-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
        if ($liveChild -and $liveChild.ProcessName -eq 'python' -and $liveChild.StartTime -ge $ownedProcess.StartTime) {
            Stop-OwnedProcessTree $liveChild
        }
    }
    $verified = Get-Process -Id $ownedProcess.Id -ErrorAction SilentlyContinue
    if ($verified -and $verified.StartTime -eq $ownedProcess.StartTime -and $verified.Path -eq $ownedProcess.Path) {
        Stop-Process -Id $verified.Id -Force
    }
}
if (Test-Path -LiteralPath $pidPath) {
    $records = Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json
    foreach ($entry in $records) {
        $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
        if ($process -and $process.Path -eq $entry.executable -and $process.StartTime.ToUniversalTime().ToString('o') -eq $entry.started_at) {
            Stop-OwnedProcessTree $process
        }
    }
    Remove-Item -LiteralPath $pidPath
}
if ($Database) {
    & (Join-Path $runtimePath 'pgsql\bin\pg_ctl.exe') -D (Join-Path $runtimePath 'pgdata') -w stop
}
Write-Output 'Recorded application processes stopped. Checkpoints will resume on the next start.'
