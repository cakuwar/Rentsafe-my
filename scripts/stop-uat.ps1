# Stops everything scripts/run-uat.ps1 started (the public link, frontend,
# backend and NLP service) and closes their windows.
#
#   .\scripts\stop-uat.ps1
#
# PostgreSQL and Redis keep running in Docker: they use little memory and
# run-uat.ps1 needs them next time. To stop them too:
#   docker compose stop db redis

# The public link goes first, so testers stop reaching a half-stopped system.
$tunnel = Get-Process cloudflared -ErrorAction SilentlyContinue
if ($tunnel) {
    $tunnel | Stop-Process -Force
    Write-Host "Public link closed."
}

# The services, found by the port they listen on. A second pass catches a
# worker left behind by a parent process (uvicorn --reload, npm).
$ports = @{ 4173 = "frontend"; 4000 = "backend"; 8000 = "NLP service" }
for ($pass = 0; $pass -lt 3; $pass++) {
    $found = $false
    foreach ($port in $ports.Keys) {
        $owners = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($id in $owners) {
            $found = $true
            Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
            if ($pass -eq 0) { Write-Host ("Stopped the {0} (port {1})." -f $ports[$port], $port) }
        }
    }
    if (-not $found) { break }
    Start-Sleep -Seconds 1
}

# The windows run-uat.ps1 opened
Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" |
    Where-Object { $_.CommandLine -like "*RentSafe UAT*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Host "RentSafe UAT is stopped. Start it again with: .\scripts\run-uat.ps1"
