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
                # Redirect stderr to a temp file (not $null) to avoid PS 5.1
                # wrapping native stderr in a terminating error.
                & taskkill.exe /PID $line /T /F 2>&1 | Out-Null
                Write-Host "Stopped PID $line (and children)"
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

# --- ensure frontend deps are installed ---
$frontend = Join-Path $root 'frontend'
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
    Write-Host "Installing frontend dependencies (first run)..." -ForegroundColor Yellow
    Push-Location $frontend
    & npm.cmd install
    Pop-Location
}

Write-Host "Starting Commute OS..." -ForegroundColor Cyan

# --- start backend (FastAPI / uvicorn) ---
$backend = Start-Process -FilePath $py `
    -ArgumentList '-m', 'uvicorn', 'api.main:app', '--host', '127.0.0.1', '--port', '8000' `
    -WorkingDirectory $root -PassThru -WindowStyle Minimized

# --- start frontend (Next.js dev server) ---
$frontendProc = Start-Process -FilePath 'npm.cmd' `
    -ArgumentList 'run', 'dev' `
    -WorkingDirectory $frontend -PassThru -WindowStyle Minimized

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
Write-Host -NoNewline "Waiting for frontend http://localhost:3000 "
$fok = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $r = Invoke-WebRequest -Uri 'http://localhost:3000' -TimeoutSec 1 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $fok = $true; break }
    } catch { }
    Write-Host -NoNewline '.'
    Start-Sleep -Seconds 1
}
Write-Host ($(if ($fok) { ' OK' } else { ' TIMEOUT' })) -ForegroundColor $(if ($fok) { 'Green' } else { 'Red' })

Write-Host ""
Write-Host "  Frontend : http://localhost:3000"      -ForegroundColor White
Write-Host "  API      : http://127.0.0.1:8000"       -ForegroundColor White
Write-Host "  Docs     : http://127.0.0.1:8000/docs"  -ForegroundColor White
Write-Host ""

if (-not $NoBrowser -and $fok) { Start-Process 'http://localhost:3000' }

Write-Host "Both servers are running. Press Ctrl+C to stop, or run '.\run.ps1 -Stop' later." -ForegroundColor Cyan

# keep this window alive; stop both servers on Ctrl+C / exit
try {
    while ($true) {
        Start-Sleep -Seconds 2
        if ($backend.HasExited -or $frontendProc.HasExited) {
            Write-Host "A server process exited. Shutting down the other." -ForegroundColor Yellow
            break
        }
    }
}
finally {
    Stop-Servers
}
