<#
    run.ps1 — One-command launcher for Commute OS (DMOS)

    Starts the FastAPI backend (port 8000) and the Next.js frontend (port 3000),
    waits until both are healthy, then opens the app in your browser.

    Usage (from repo root):
        .\run.ps1                # start both, open browser
        .\run.ps1 -NoBrowser     # start both, don't open browser
        .\run.ps1 -Stop          # stop servers started by this script

    Press Ctrl+C in this window to stop both servers.
#>
[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$Stop
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$pidFile = Join-Path $env:TEMP 'dmos_run_pids.txt'
$logDir = Join-Path $root '.run-logs'

# Sessions opened before Node was installed may not have its PATH entry.
$nodeDir = 'C:\Program Files\nodejs'
$nodeExe = Join-Path $nodeDir 'node.exe'
$npmCmd = Join-Path $nodeDir 'npm.cmd'
if (Test-Path $nodeExe) {
    $env:Path = "$nodeDir;$env:Path"
}

function Stop-Servers {
    if (Test-Path $pidFile) {
        foreach ($line in Get-Content $pidFile) {
            if ($line -match '^\d+$') {
                # Skip PIDs that are already gone (e.g. from a previous run) so
                # taskkill doesn't emit a NativeCommandError under ErrorAction=Stop.
                if (-not (Get-Process -Id $line -ErrorAction SilentlyContinue)) {
                    continue
                }
                # /T kills the whole process tree (npm.cmd shim spawns a child
                # node process; Stop-Process on the shim alone would orphan it).
                $kill = Start-Process -FilePath 'taskkill.exe' `
                    -ArgumentList '/PID', $line, '/T', '/F' `
                    -WindowStyle Hidden -Wait -PassThru
                if ($kill.ExitCode -eq 0) {
                    Write-Host "Stopped PID $line (and children)"
                } else {
                    Write-Warning "Could not stop PID $line (taskkill exit $($kill.ExitCode))."
                }
            }
        }
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    } else {
        Write-Host "No running servers recorded."
    }
}

if ($Stop) { Stop-Servers; return }

# --- locate the venv Python ---
$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    Write-Error "Virtual env not found at $py. Create it with: python -m venv .venv ; .\.venv\Scripts\Activate.ps1 ; pip install -r requirements.txt"
    return
}
if (-not (Test-Path $nodeExe)) {
    Write-Error "Node.js was not found at $nodeExe. Install Node.js 20+ and run this script again."
    return
}

# --- ensure frontend deps are installed ---
$frontend = Join-Path $root 'frontend'
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
    Write-Host "Installing frontend dependencies (first run)..." -ForegroundColor Yellow
    Push-Location $frontend
    & $npmCmd install
    Pop-Location
}
$nextCli = 'node_modules\next\dist\bin\next'
$nextCliPath = Join-Path $frontend $nextCli
if (-not (Test-Path $nextCliPath)) {
    Write-Error "Next.js CLI was not found after dependency installation: $nextCliPath"
    return
}
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

Write-Host "Starting Commute OS..." -ForegroundColor Cyan

# --- start backend (FastAPI / uvicorn) ---
$backend = Start-Process -FilePath $py `
    -ArgumentList '-m', 'uvicorn', 'api.main:app', '--host', '127.0.0.1', '--port', '8000' `
    -WorkingDirectory $root -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDir 'backend.out.log') `
    -RedirectStandardError (Join-Path $logDir 'backend.err.log')

# --- start frontend (Next.js dev server) ---
$frontendProc = Start-Process -FilePath $nodeExe `
    -ArgumentList $nextCli, 'dev', '-H', '127.0.0.1', '-p', '3000' `
    -WorkingDirectory $frontend -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDir 'frontend.out.log') `
    -RedirectStandardError (Join-Path $logDir 'frontend.err.log')

# record PIDs so -Stop can clean up
Set-Content -Path $pidFile -Value @($backend.Id, $frontendProc.Id)

# --- wait for backend health ---
Write-Host -NoNewline "Waiting for backend  http://127.0.0.1:8000 "
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 1 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch { }
    Write-Host -NoNewline '.'
    Start-Sleep -Seconds 1
}
Write-Host ($(if ($ok) { ' OK' } else { ' TIMEOUT' })) -ForegroundColor $(if ($ok) { 'Green' } else { 'Red' })

# --- wait for frontend ---
Write-Host -NoNewline "Waiting for frontend http://127.0.0.1:3000 "
$fok = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:3000' -TimeoutSec 1 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $fok = $true; break }
    } catch { }
    Write-Host -NoNewline '.'
    Start-Sleep -Seconds 1
}
Write-Host ($(if ($fok) { ' OK' } else { ' TIMEOUT' })) -ForegroundColor $(if ($fok) { 'Green' } else { 'Red' })

if (-not $ok -or -not $fok) {
    Write-Host ""
    Write-Host "Startup failed. Recent server errors:" -ForegroundColor Red
    Get-Content (Join-Path $logDir 'backend.err.log') -Tail 30 -ErrorAction SilentlyContinue
    Get-Content (Join-Path $logDir 'frontend.err.log') -Tail 30 -ErrorAction SilentlyContinue
    Stop-Servers
    exit 1
}

# Next.js may hand off to a worker process. Record the actual listening PIDs so
# -Stop and Ctrl+C clean up the services rather than an exited launcher shim.
$listenerPids = Get-NetTCPConnection -State Listen -LocalPort 8000, 3000 `
    -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
if ($listenerPids) {
    Set-Content -Path $pidFile -Value $listenerPids
}

Write-Host ""
Write-Host "  Frontend : http://127.0.0.1:3000"      -ForegroundColor White
Write-Host "  API      : http://127.0.0.1:8000"       -ForegroundColor White
Write-Host "  Docs     : http://127.0.0.1:8000/docs"  -ForegroundColor White
Write-Host ""

if (-not $NoBrowser -and $fok) { Start-Process 'http://127.0.0.1:3000' }

Write-Host "Both servers are running. Press Ctrl+C to stop, or run '.\run.ps1 -Stop' later." -ForegroundColor Cyan

# keep this window alive; stop both servers on Ctrl+C / exit
try {
    while ($true) {
        Start-Sleep -Seconds 2
        $backendAlive = $false
        $frontendAlive = $false
        try {
            $backendAlive = (Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 1 -UseBasicParsing).StatusCode -eq 200
        } catch { }
        try {
            $frontendAlive = (Invoke-WebRequest -Uri 'http://127.0.0.1:3000' -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200
        } catch { }
        if (-not $backendAlive -or -not $frontendAlive) {
            Write-Host "A server process exited. Shutting down the other." -ForegroundColor Yellow
            break
        }
    }
}
finally {
    Stop-Servers
}
