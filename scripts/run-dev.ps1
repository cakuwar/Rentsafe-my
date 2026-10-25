$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot

Write-Host "Starting PostgreSQL and Redis..."
docker compose -f (Join-Path $root "docker-compose.yml") up -d db redis

function Start-ServiceTerminal($title, $directory, $command) {
    $windowCommand = "Set-Location '$directory'; `$Host.UI.RawUI.WindowTitle = '$title'; $command"
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command", $windowCommand
    ) | Out-Null
}

Start-ServiceTerminal "RentSafe Backend - 4000" (Join-Path $root "backend") "npm run dev"
Start-ServiceTerminal "RentSafe NLP - 8000" (Join-Path $root "nlp-service") ".\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
Start-ServiceTerminal "RentSafe Frontend - 5173" (Join-Path $root "frontend") "npm run dev"

Write-Host ""
Write-Host "Services are starting in separate terminals:"
Write-Host "  Frontend: http://localhost:5173"
Write-Host "  Backend:  http://localhost:4000"
Write-Host "  NLP/OCR:  http://localhost:8000/docs"
Write-Host "  Postgres: localhost:5432"
Write-Host "  Redis:    localhost:6379"