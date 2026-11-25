<#
E5: timing and 10 concurrent users, on a SEPARATE copy of the stack.

  Full run (asks for the API keys, hidden input):
    powershell -ExecutionPolicy Bypass -File experiments\scripts\e5\RUN_E5.ps1
  Free check (no keys, 2 cases, 20 s of load):
    powershell -ExecutionPolicy Bypass -File experiments\scripts\e5\RUN_E5.ps1 -Smoke

What it touches:
  - a code copy in ~\rentsafe_experiments_data\e5_stack (no .env files are copied)
  - docker compose project "rentsafe_exp": its own PostgreSQL (127.0.0.1:5433) and
    Redis (127.0.0.1:6380), new volumes, removed again at the end
  - the model service copy on 127.0.0.1:8100 and the backend copy on 127.0.0.1:4100
It never stops, restarts or connects to the demo containers (rentsafe-my-*), and never
writes to the repo outside experiments\. Pre- and post-flight records prove it.
#>
#   Test A only (e.g. to repeat it with a corrected search key):
#     powershell -ExecutionPolicy Bypass -File experiments\scripts\e5\RUN_E5.ps1 -OnlyA
param([switch]$Smoke, [switch]$KeepStack, [switch]$OnlyA)

# "Continue", not "Stop": in Windows PowerShell 5.1, "Stop" turns the progress lines
# that docker, node and robocopy write to stderr into fatal errors. Failures are
# caught explicitly instead (Native checks exit codes; cmdlets use -ErrorAction Stop).
$ErrorActionPreference = "Continue"
$Repo    = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..") -ErrorAction Stop).Path
$Exp     = Join-Path $Repo "experiments"
$Priv    = Join-Path $env:USERPROFILE "rentsafe_experiments_data"
$Stack   = Join-Path $Priv "e5_stack"
$Tag     = (Get-Date -Format "yyyyMMdd'T'HHmmss") + $(if ($Smoke) { "_smoke" } else { "" }) + $(if ($OnlyA) { "_testA" } else { "" })
$PrivOut = Join-Path $Priv "e5\$Tag"
$PubOut  = Join-Path $Exp "results\e5\$Tag"
$Py      = Join-Path $Repo "nlp-service\.venv\Scripts\python.exe"
$Project = "rentsafe_exp"
$Compose = Join-Path $Stack "compose.exp.yml"
$DbUrl   = "postgres://rentsafe:e5_local_only@127.0.0.1:5433/rentsafe_exp"
$Tesseract = "C:\Program Files\Tesseract-OCR\tesseract.exe"
$Procs   = @{}

function Say($m) { Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m) }
function Native($what) { if ($LASTEXITCODE -ne 0) { throw "$what failed (exit $LASTEXITCODE)" } }

# ------------------------------------------------------------------ safety checks
if ($Project -eq "rentsafe-my") { throw "project name must differ from the demo project" }
if (-not $Stack.StartsWith($Priv)) { throw "stack folder must be inside $Priv" }
foreach ($p in 5433, 6380, 8100, 4100) {
    if (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) { throw "port $p is already in use; stop and check what is running" }
}
foreach ($c in "rentsafe-my-db-1", "rentsafe-my-redis-1") {
    $state = docker inspect $c --format "{{.State.Running}}" 2>$null
    if ($state -ne "true") { Write-Warning "demo container $c is not running (this script does not need it, and will not start it)" }
}
New-Item -ItemType Directory -Force $PrivOut, $PubOut | Out-Null

# ------------------------------------------------------------------ pre-flight
$HashFiles = Get-Content (Join-Path $Exp "proof\preflight.txt") |
    ForEach-Object { if ($_ -match '^[0-9a-f]{64} \*(.+)$') { $Matches[1] } }
function Get-State {
    $l = @("--- git status --porcelain"); $l += @(git -C $Repo status --porcelain)
    $l += "--- git rev-parse HEAD"; $l += (git -C $Repo rev-parse HEAD)
    $l += "--- sha256: model weights and price baseline (file list from proof\preflight.txt)"
    foreach ($rel in $HashFiles) { $l += ("{0} *{1}" -f (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Repo $rel)).Hash.ToLower(), $rel) }
    $l += "--- demo containers (id, start time, restart count)"
    foreach ($c in "rentsafe-my-db-1", "rentsafe-my-redis-1") { $l += (docker inspect $c --format "{{.Name}} {{.Id}} started={{.State.StartedAt}} restarts={{.RestartCount}}" 2>$null) }
    $l += "--- demo volumes"; $l += @(docker volume ls --format "{{.Name}}" | Where-Object { $_ -like "rentsafe-my_*" })
    return $l
}
Say "pre-flight (hashing $($HashFiles.Count) files)"
$Pre = Get-State
$Pre | Set-Content -Encoding utf8 (Join-Path $Exp "proof\e5_preflight_$Tag.txt")

# ------------------------------------------------------------------ keys (full run only)
$Keys = @{}
$KeyNames = "OPENAI_API_KEY", "SERPER_API_KEY", "SERPAPI_API_KEY", "GEMINI_API_KEY"
foreach ($k in $KeyNames) {
    $v = [Environment]::GetEnvironmentVariable($k, "Process")
    if (-not $Smoke -and -not $v -and $k -ne "SERPAPI_API_KEY") {
        $s = Read-Host "Paste $k (hidden; press Enter to skip)" -AsSecureString
        $v = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
    }
    if ($Smoke) { $v = $null }
    if ($v) { $Keys[$k] = $v }
    Remove-Item "env:$k" -ErrorAction SilentlyContinue   # only ever passed to the backend copy, below
}
Say ("keys present: " + $(if ($Keys.Count) { ($Keys.Keys | Sort-Object) -join ", " } else { "none (smoke run: no paid calls)" }))
$Models = @{
    NARRATIVE_PROVIDER    = $(if ($env:NARRATIVE_PROVIDER) { $env:NARRATIVE_PROVIDER } else { "openai" })
    OPENAI_MODEL          = $(if ($env:OPENAI_MODEL) { $env:OPENAI_MODEL } else { "gpt-4o-mini" })
    LLM_VERIFIER_PROVIDER = $(if ($env:LLM_VERIFIER_PROVIDER) { $env:LLM_VERIFIER_PROVIDER } else { "gemini" })
    GEMINI_MODEL          = $(if ($env:GEMINI_MODEL) { $env:GEMINI_MODEL } else { "gemini-3.5-flash-lite" })
}
Say ("models: " + (($Models.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join "  "))

function Set-Env([hashtable]$h) { foreach ($e in $h.GetEnumerator()) { Set-Item "env:$($e.Name)" $e.Value } }
function Clear-Env([string[]]$names) { foreach ($n in $names) { Remove-Item "env:$n" -ErrorAction SilentlyContinue } }

function Wait-Http($url, $seconds) {
    $end = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $end) {
        try { Invoke-RestMethod $url -TimeoutSec 5 | Out-Null; return } catch { Start-Sleep 2 }
    }
    throw "$url did not answer within $seconds s"
}

function Stop-Tree($name) {
    if ($Procs[$name]) { & taskkill /PID $Procs[$name].Id /T /F 2>&1 | Out-Null; $Procs.Remove($name) }
}

$BackendEnvNames = @("PORT", "DATABASE_URL", "REDIS_URL", "NLP_SERVICE_URL", "PGHOST", "PGPORT", "FRONTEND_ORIGIN") + $KeyNames + @($Models.Keys)
function Start-Backend([string]$label, [string[]]$keysWanted, [bool]$cache) {
    $h = @{ PORT = "4100"; DATABASE_URL = $DbUrl; NLP_SERVICE_URL = "http://127.0.0.1:8100"; PGHOST = "127.0.0.1"; PGPORT = "5433";
            FRONTEND_ORIGIN = "http://localhost:5173" } + $Models
    if ($cache) { $h.REDIS_URL = "redis://127.0.0.1:6380" }
    foreach ($k in $keysWanted) { if ($Keys[$k]) { $h[$k] = $Keys[$k] } }
    if ($h.DATABASE_URL -notmatch ':5433/') { throw "DATABASE_URL must point at the experiment database" }
    if (Test-Path (Join-Path $Stack "backend\.env")) { throw "a .env file appeared in the backend copy; refusing to start" }
    Clear-Env $BackendEnvNames; Set-Env $h
    $Procs.backend = Start-Process node -ArgumentList "src/server.js" -WorkingDirectory (Join-Path $Stack "backend") -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $PrivOut "backend_$label.log") -RedirectStandardError (Join-Path $PrivOut "backend_$label.err.log")
    Clear-Env $BackendEnvNames
    Wait-Http "http://127.0.0.1:4100/api/health" 60
    Say "backend ($label) up, pid $($Procs.backend.Id); cache $(if ($cache) {'on'} else {'off'}); keys: $((@($keysWanted | Where-Object { $Keys[$_] })) -join ', ')"
}

$Summary = [ordered]@{ tag = $Tag; smoke = [bool]$Smoke }
$ok = $false
try {
    # -------------------------------------------------------------- copy
    Say "copying the code to $Stack (no .env files)"
    $copies = @(
        @("backend", "backend", @("/XF", ".env", "/XD", "tests", "coverage")),
        @("database", "database", @()),
        @("nlp-service\app", "nlp-service\app", @("/XD", "__pycache__")),
        @("nlp-service\tessdata", "nlp-service\tessdata", @()),
        @("nlp-service\models\xlm-roberta-scam-v3-run1", "nlp-service\models\xlm-roberta-scam-v3-run1", @())
    )
    foreach ($c in $copies) {
        & robocopy (Join-Path $Repo $c[0]) (Join-Path $Stack $c[1]) /E /NFL /NDL /NJH /NJS /NP @($c[2]) | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "robocopy $($c[0]) failed ($LASTEXITCODE)" }
    }
    Get-ChildItem $Stack -Recurse -Force -Filter ".env" | ForEach-Object { throw "unexpected .env in the copy: $($_.FullName)" }
    $w1 = (Get-FileHash (Join-Path $Repo "nlp-service\models\xlm-roberta-scam-v3-run1\model.safetensors")).Hash
    $w2 = (Get-FileHash (Join-Path $Stack "nlp-service\models\xlm-roberta-scam-v3-run1\model.safetensors")).Hash
    if ($w1 -ne $w2) { throw "the copied weights differ from the deployed weights" }
    $Summary.weights_sha256 = $w1.ToLower()

    # -------------------------------------------------------------- database and Redis (rentsafe_exp only)
@"
name: $Project
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_USER: rentsafe
      POSTGRES_PASSWORD: e5_local_only
      POSTGRES_DB: rentsafe_exp
    ports: ["127.0.0.1:5433:5432"]
    volumes:
      - e5-db:/var/lib/postgresql/data
      - ./database/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql:ro
  redis:
    image: redis:7-alpine
    ports: ["127.0.0.1:6380:6379"]
volumes:
  e5-db:
"@ | Set-Content -Encoding ascii $Compose
    Say "starting $Project (its own PostgreSQL and Redis)"
    docker compose -p $Project -f $Compose up -d 2>&1 | Out-Null; Native "docker compose up"
    $end = (Get-Date).AddSeconds(120)
    do {
        Start-Sleep 2
        $logs = (docker logs "$Project-db-1" 2>&1 | Out-String)
        $ready = ($logs -match "PostgreSQL init process complete") -and ((docker exec "$Project-db-1" pg_isready -U rentsafe -d rentsafe_exp 2>&1) -match "accepting")
    } until ($ready -or (Get-Date) -gt $end)
    if (-not $ready) { throw "experiment database did not become ready" }

    Say "migrations and seeds (price baseline, lexicon) into the experiment database"
    Clear-Env $BackendEnvNames
    Set-Env @{ DATABASE_URL = $DbUrl; PGHOST = "127.0.0.1"; PGPORT = "5433" }
    Push-Location (Join-Path $Stack "backend")
    try {
        node src/db/migrate.js 2>&1 | Out-File -Encoding utf8 (Join-Path $PrivOut "migrate.log"); Native "migrate"
        node src/db/seed.js 2>&1 | Out-File -Encoding utf8 (Join-Path $PrivOut "seed.log"); Native "seed"
    } finally { Pop-Location; Clear-Env @("DATABASE_URL", "PGHOST", "PGPORT") }
    $Summary.baseline_rows = (docker exec "$Project-db-1" psql -U rentsafe -d rentsafe_exp -tAc "select (select count(*) from price_baseline) || ' whole-unit strata, ' || (select count(*) from room_price_baseline) || ' room strata'").Trim()
    Say "baseline loaded: $($Summary.baseline_rows)"

    # -------------------------------------------------------------- model service copy
    Say "starting the model service copy (loads the weights; can take a minute)"
    Set-Env @{ TESSERACT_CMD = $Tesseract; HF_HUB_OFFLINE = "1"; TRANSFORMERS_OFFLINE = "1";
               FINETUNED_MODEL_DIR = (Join-Path $Stack "nlp-service\models\xlm-roberta-scam-v3-run1") }
    $nlpDir = Join-Path $Stack "nlp-service"
    $Procs.nlp = Start-Process $Py -ArgumentList "-I -B -m uvicorn app.main:app --app-dir `"$nlpDir`" --host 127.0.0.1 --port 8100" `
        -WorkingDirectory $nlpDir -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $PrivOut "nlp.log") -RedirectStandardError (Join-Path $PrivOut "nlp.err.log")
    Clear-Env @("TESSERACT_CMD", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "FINETUNED_MODEL_DIR")
    $t = Get-Date; Wait-Http "http://127.0.0.1:8100/health" 300
    $Summary.model_service_start_s = [math]::Round(((Get-Date) - $t).TotalSeconds, 1)
    Say "model service up after $($Summary.model_service_start_s) s"

    # -------------------------------------------------------------- Test A: full system, cold cache
    Start-Backend "A" @("OPENAI_API_KEY", "SERPER_API_KEY", "SERPAPI_API_KEY", "GEMINI_API_KEY") $true
    Say "Test A: 15 blind cases, one at a time"
    & $Py -I -B (Join-Path $PSScriptRoot "e5_run.py") --phase A --private $PrivOut --public $PubOut --pids "$($Procs.nlp.Id),$($Procs.backend.Id)" @(if ($Smoke) { "--smoke" })
    Native "Test A"
    Stop-Tree "backend"

    # -------------------------------------------------------------- Test B: load, explanation on, no search keys, cache off
    if ($OnlyA) {
        Say "Test B skipped (-OnlyA)"
    } else {
        Start-Backend "B" @("OPENAI_API_KEY") $false
        Say "Test B: concurrent users (no agent identifiers; search and judge keys withheld; cache off so every request is new)"
        & $Py -I -B (Join-Path $PSScriptRoot "e5_run.py") --phase B --private $PrivOut --public $PubOut --pids "$($Procs.nlp.Id),$($Procs.backend.Id)" @(if ($Smoke) { "--smoke" })
        Native "Test B"
    }
    $ok = $true
}
finally {
    Say "stopping the experiment processes"
    Stop-Tree "backend"; Stop-Tree "nlp"
    if (-not $KeepStack) {
        Say "removing ONLY the $Project project (containers and its volume)"
        docker compose -p $Project -f $Compose down -v 2>&1 | Out-Null
    }
    Clear-Env ($BackendEnvNames + @("TESSERACT_CMD", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "FINETUNED_MODEL_DIR"))
    $Keys.Clear()

    # ---------------------------------------------------------- post-flight
    Say "post-flight"
    $Post = Get-State
    $Post | Set-Content -Encoding utf8 (Join-Path $Exp "proof\e5_postflight_$Tag.txt")
    $diff = Compare-Object $Pre $Post
    $left = @(docker ps -a --format "{{.Names}}" | Where-Object { $_ -like "$Project*" }) + @(docker volume ls --format "{{.Name}}" | Where-Object { $_ -like "$Project*" })
    $Summary.postflight_unchanged = (-not $diff)
    $Summary.experiment_project_removed = ($left.Count -eq 0)
    $Summary.completed = $ok
    $Summary | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $PubOut "run.json")
    if ($diff) { Write-Warning "POST-FLIGHT DIFFERS FROM PRE-FLIGHT:"; $diff | Format-Table -AutoSize | Out-String | Write-Host }
    else { Say "post-flight matches pre-flight: repo, weights, baseline files and demo containers unchanged" }
    if ($left.Count) { Write-Warning "left over from ${Project}: $($left -join ', ')" } elseif (-not $KeepStack) { Say "$Project removed" }
    Say "results (no chat text): $PubOut"
    Say "private logs and full responses: $PrivOut"
}
