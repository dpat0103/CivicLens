# start.ps1
#
# Launches the CivicLens backend (FastAPI) and frontend (Next.js) each
# in their own PowerShell window, so you don't have to open two
# terminals and remember the commands every time.
#
# Usage: from the civiclens root folder, run:
#   .\start.ps1
#
# If PowerShell blocks it with an execution-policy error, run this
# once first (only affects the current window):
#   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

$root = $PSScriptRoot

Write-Host "Starting CivicLens backend (http://localhost:8000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$root\backend'; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8000"
)

Start-Sleep -Seconds 2

Write-Host "Starting CivicLens frontend (http://localhost:3000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$root\frontend'; npm run dev"
)

Write-Host ""
Write-Host "Both servers are starting in their own windows." -ForegroundColor Green
Write-Host "  Backend:  http://localhost:8000/docs" -ForegroundColor Green
Write-Host "  Frontend: http://localhost:3000" -ForegroundColor Green
Write-Host ""
Write-Host "Close those windows (or Ctrl+C inside them) to stop the servers." -ForegroundColor DarkGray
