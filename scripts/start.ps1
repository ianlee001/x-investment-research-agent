param([switch]$Dev)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    & uv sync --frozen
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
}
& $pythonExe scripts\setup_local.py
if ($LASTEXITCODE -ne 0) { throw 'Local PostgreSQL startup failed.' }
& $pythonExe -m app.cli init
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html')) -or $Dev) {
    Push-Location -LiteralPath (Join-Path $projectRoot 'frontend')
    try {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
}
$runtimePath = Join-Path $projectRoot '.runtime'
$pidPath = Join-Path $runtimePath 'app-processes.json'
if (Test-Path -LiteralPath $pidPath) {
    $previous = Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json
    foreach ($entry in $previous) {
        if (Get-Process -Id $entry.pid -ErrorAction SilentlyContinue) {
            throw 'A recorded application process is still running. Use scripts\stop.ps1 first.'
        }
    }
}
$records = @()
foreach ($role in @('worker', 'api')) {
    $process = Start-Process -FilePath $pythonExe -ArgumentList @('-m', 'app.cli', $role) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimePath "$role.stdout.log") -RedirectStandardError (Join-Path $runtimePath "$role.stderr.log")
    $records += @{ pid = $process.Id; role = $role; executable = $pythonExe; started_at = $process.StartTime.ToUniversalTime().ToString('o') }
}
ConvertTo-Json -InputObject $records | Set-Content -LiteralPath $pidPath -Encoding utf8
Write-Output 'Starting X Research. Open http://127.0.0.1:8765 after the API is ready.'
Write-Output 'Logs: .runtime\api.stderr.log and .runtime\worker.stderr.log'
