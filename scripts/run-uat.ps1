# Runs RentSafe MY for user acceptance testing (UAT) and shares it on a public
# https link, so testers can use it from their own phone or laptop while it
# runs on this machine.
#
#   .\scripts\run-uat.ps1
#
# What it does:
#   1. starts PostgreSQL and Redis (Docker)
#   2. starts the backend and the NLP service, each in its own window, without
#      auto-reload, so editing a file mid-session cannot restart them and drop
#      a tester's analysis (a service already running is reused)
#   3. builds the frontend and serves the built version (vite preview, port
#      4173), which passes /api calls on to the backend (frontend/vite.config.js)
#   4. opens a Cloudflare quick tunnel to port 4173 and prints the public link
#
# Only port 4173 is shared. The backend, NLP service and database stay
# private; testers reach the API only through the /api proxy.
#
# Keep this machine on, awake and online for the whole session. The link
# changes every time the tunnel starts. To stop, run .\scripts\stop-uat.ps1
# (or close the windows this script opened).
#
# Needs cloudflared once:  winget install --id Cloudflare.cloudflared

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root = Split-Path -Parent $PSScriptRoot
$frontendPort = 4173

function Start-ServiceTerminal($title, $directory, $command) {
    $windowCommand = "Set-Location '$directory'; `$Host.UI.RawUI.WindowTitle = '$title'; $command"
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command", $windowCommand
    ) | Out-Null
}

function Test-Listening($port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
}

function Wait-Http($url, $seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Seconds 2
    }
    return $false
}

# --- cloudflared -------------------------------------------------------------
$cloudflared = $null
$onPath = Get-Command cloudflared -ErrorAction SilentlyContinue
if ($onPath) {
    $cloudflared = $onPath.Source
} else {
    # winget does not update PATH for terminals that were already open
    foreach ($candidate in @(
        "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe",
        "$env:ProgramFiles\cloudflared\cloudflared.exe"
    )) {
        if (Test-Path $candidate) { $cloudflared = $candidate; break }
    }
}
if (-not $cloudflared) {
    Write-Host "cloudflared is not installed. Install it once with:" -ForegroundColor Red
    Write-Host "  winget install --id Cloudflare.cloudflared"
    exit 1
}

if (Test-Listening $frontendPort) {
    Write-Host "Port $frontendPort is already in use, probably by an earlier run of this script." -ForegroundColor Red
    Write-Host "Close the old 'RentSafe UAT' windows and run this script again."
    exit 1
}

# --- 1. database and cache ---------------------------------------------------
Write-Host "Starting PostgreSQL and Redis..."
docker compose -f (Join-Path $root "docker-compose.yml") up -d db redis
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker could not start the database. Is Docker Desktop running?" -ForegroundColor Red
    exit 1
}

# --- 2. backend and NLP service ----------------------------------------------
if (Test-Listening 4000) {
    Write-Host "Backend already running on port 4000, reusing it."
} else {
    Start-ServiceTerminal "RentSafe UAT - backend 4000" (Join-Path $root "backend") "npm start"
}
if (Test-Listening 8000) {
    Write-Host "NLP service already running on port 8000, reusing it."
} else {
    Start-ServiceTerminal "RentSafe UAT - NLP 8000" (Join-Path $root "nlp-service") ".\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"
}

# --- 3. frontend: build, then serve the build ---------------------------------
Write-Host "Building the frontend..."
Push-Location (Join-Path $root "frontend")
try {
    npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Frontend build failed, see the output above." -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}
Start-ServiceTerminal "RentSafe UAT - frontend $frontendPort" (Join-Path $root "frontend") "npm run preview -- --port $frontendPort --strictPort"

Write-Host "Waiting for the services (the NLP model takes a minute to load)..."
$checks = @(
    @{ Name = "backend";      Url = "http://localhost:4000/api/health"; Seconds = 90 },
    @{ Name = "NLP service";  Url = "http://localhost:8000/health";     Seconds = 300 },
    @{ Name = "frontend";     Url = "http://localhost:$frontendPort/";  Seconds = 60 }
)
foreach ($check in $checks) {
    if (Wait-Http $check.Url $check.Seconds) {
        Write-Host ("  {0} is up" -f $check.Name)
    } else {
        Write-Host ("  {0} did not answer at {1}. Check its window for errors." -f $check.Name, $check.Url) -ForegroundColor Red
        exit 1
    }
}

# --- 4. public link -----------------------------------------------------------
$log = Join-Path $env:TEMP "rentsafe-uat-tunnel.log"
if (Test-Path $log) { Remove-Item $log -Force }
Start-ServiceTerminal "RentSafe UAT - public link" $root "& '$cloudflared' tunnel --no-autoupdate --url http://localhost:$frontendPort --logfile '$log'"

Write-Host "Opening the public link..."
$url = $null
$deadline = (Get-Date).AddSeconds(60)
while (-not $url -and (Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    if (Test-Path $log) {
        $match = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
        if ($match) { $url = $match.Matches[0].Value }
    }
}
if (-not $url) {
    Write-Host "The tunnel did not report a link. Check the 'public link' window." -ForegroundColor Red
    exit 1
}

# A new link takes a few seconds to go live. Checking it too early can make
# Windows cache "not found" for this machine for a few minutes, so wait first.
Start-Sleep -Seconds 8
$live = Wait-Http "$url/api/health" 60

Set-Clipboard -Value $url
Write-Host ""
Write-Host "RentSafe MY is live for testers at:" -ForegroundColor Green
Write-Host "  $url" -ForegroundColor Green
Write-Host "(copied to the clipboard)"
if (-not $live) {
    Write-Host "This machine could not open the link yet. Try it on your phone (mobile data) before sharing it." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Keep this laptop on, awake and online until the session ends."
Write-Host "The link changes each time this script runs: update it in the Google Form."
Write-Host "To stop: .\scripts\stop-uat.ps1 (or close the 'RentSafe UAT' windows)."
