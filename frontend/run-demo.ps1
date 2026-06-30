# Helix demo launcher — starts the backend (:8000) and the React app (:5173), opens the browser.
# Run from anywhere:  ./frontend/run-demo.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $root "backend"
$app = Join-Path $PSScriptRoot "app"
$py = Join-Path $backend ".venv/Scripts/python.exe"

Write-Host "Starting Helix API on http://127.0.0.1:8000 ..." -ForegroundColor Yellow
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","api.main:app","--port","8000" -WorkingDirectory $backend

if (-not (Test-Path (Join-Path $app "node_modules"))) {
  Write-Host "Installing frontend dependencies (first run) ..." -ForegroundColor Yellow
  Start-Process -FilePath "npm" -ArgumentList "install" -WorkingDirectory $app -Wait -NoNewWindow
}

Write-Host "Starting the Helix app on http://localhost:5173 ..." -ForegroundColor Yellow
Start-Process -FilePath "npm" -ArgumentList "run","dev" -WorkingDirectory $app

Start-Sleep -Seconds 4
Start-Process "http://localhost:5173"
Write-Host "Helix is up. App: http://localhost:5173   API: http://127.0.0.1:8000/health" -ForegroundColor Green
Write-Host "(Close the two spawned windows to stop. The legacy no-build demo is still at frontend/helix.html.)"
