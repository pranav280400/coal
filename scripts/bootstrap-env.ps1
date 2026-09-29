<#
.SYNOPSIS
  Creates .env from .env.example and fills in every secret the CoalMineGov stack needs.

.DESCRIPTION
  Run this once before your first `docker compose up`:

      .\scripts\bootstrap-env.ps1

  Safe to re-run: values that are already set are never overwritten - only blank keys get a
  freshly generated value. Nothing leaves your machine; the secrets are generated locally
  inside the backend container image (python -m app.cli generate-secrets).

  This deliberately uses plain `docker build` / `docker run` rather than `docker compose`,
  because compose now refuses to start until .env is filled in - which is what this script
  is for.
#>

[CmdletBinding()]
param(
    # Skip the interactive administrator prompts (useful in CI).
    [switch]$NonInteractive
)

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

$EnvFile = '.env'
$Image   = 'coalminegov/backend:bootstrap'

function Write-Step { param([string]$Text) Write-Host "`n==> $Text" -ForegroundColor Cyan }
function Write-Info { param([string]$Text) Write-Host "  $Text" }

# --------------------------------------------------------------- preconditions
docker info *> $null
if (-not $?) {
    Write-Host 'ERROR: Docker is not running.' -ForegroundColor Red
    Write-Host '       Start Docker Desktop, wait for the whale icon to stop animating,'
    Write-Host '       then run this script again.'
    exit 1
}

# ------------------------------------------------------------------- .env file
Write-Step "Preparing $EnvFile"
if (-not (Test-Path $EnvFile)) {
    Copy-Item '.env.example' $EnvFile
    Write-Info "created $EnvFile from .env.example"
} else {
    Copy-Item $EnvFile "$EnvFile.backup" -Force
    Write-Info "$EnvFile already exists - backed it up to $EnvFile.backup"
}

# ------------------------------------------------------------- backend image
Write-Step 'Building the backend image (the first run takes a few minutes)'
docker build -t $Image ./backend
if ($LASTEXITCODE -ne 0) { Write-Host 'ERROR: backend image build failed.' -ForegroundColor Red; exit 1 }

function Invoke-Gen {
    param([string[]]$Arguments)
    $out = docker run --rm --entrypoint python $Image @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Secret generation failed inside the backend container.' }
    return $out
}

# --------------------------------------------------------------- .env editing
# Read once, edit in memory, write once - so a value containing '/', '+' or '=' is never
# mangled by regex replacement of the whole file.
$lines = [System.IO.File]::ReadAllLines((Resolve-Path $EnvFile))

function Set-EnvValue {
    param([string]$Key, [string]$Value)
    $changed = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        # Match `KEY=` with nothing after it but optional whitespace and a trailing comment.
        if ($lines[$i] -match "^$([regex]::Escape($Key))=\s*(#.*)?$") {
            $lines[$i] = "$Key=$Value"
            $changed = $true
            break
        }
    }
    if ($changed) { Write-Info "set $Key" } else { Write-Info "kept existing $Key" }
}

Write-Step 'Generating secrets'
foreach ($line in (Invoke-Gen @('-m', 'app.cli', 'generate-secrets'))) {
    if ($line -match '^\s*#' -or [string]::IsNullOrWhiteSpace($line)) { continue }
    $idx = $line.IndexOf('=')
    if ($idx -lt 1) { continue }
    Set-EnvValue $line.Substring(0, $idx) $line.Substring($idx + 1)
}

# --------------------------------------------------- first administrator account
if (-not $NonInteractive) {
    Write-Step 'First administrator account'

    $needsEmail = $lines | Where-Object { $_ -match '^BOOTSTRAP_ADMIN_EMAIL=\s*(#.*)?$' }
    if ($needsEmail) {
        $adminEmail = Read-Host '  Admin e-mail address'
        Set-EnvValue 'BOOTSTRAP_ADMIN_EMAIL' $adminEmail
    } else {
        Write-Info 'kept existing BOOTSTRAP_ADMIN_EMAIL'
    }

    $needsPassword = $lines | Where-Object { $_ -match '^BOOTSTRAP_ADMIN_PASSWORD=\s*(#.*)?$' }
    if ($needsPassword) {
        Write-Host '  Admin password: 10+ characters with upper case, lower case, a digit and a symbol.'
        $secure = Read-Host '  Admin password (press Enter to generate one)' -AsSecureString
        $plain = [System.Net.NetworkCredential]::new('', $secure).Password
        if ([string]::IsNullOrWhiteSpace($plain)) {
            $plain = (Invoke-Gen @('-c', 'import secrets,string; a=string.ascii_letters+string.digits; print("Cmg#"+"".join(secrets.choice(a) for _ in range(16)))')) | Select-Object -First 1
            Write-Info "generated one - it is saved in $EnvFile as BOOTSTRAP_ADMIN_PASSWORD"
        }
        Set-EnvValue 'BOOTSTRAP_ADMIN_PASSWORD' $plain
    } else {
        Write-Info 'kept existing BOOTSTRAP_ADMIN_PASSWORD'
    }
}

# .env must stay LF-only: Docker Compose keeps trailing \r as part of the value, which
# silently corrupts passwords.
[System.IO.File]::WriteAllText(
    (Join-Path (Get-Location) $EnvFile),
    ($lines -join "`n") + "`n",
    (New-Object System.Text.UTF8Encoding $false))

Write-Host @'

==> Done. .env is ready.

Next:
    docker compose up -d --build
    docker compose ps                                     # wait for api + web = healthy
    docker compose exec api python -m app.cli seed-demo    # optional demo data

Then open http://localhost:3000 and sign in with the admin e-mail + password above.

AI features (assistant, semantic search, AI severity suggestions) stay off until you point
VLLM_CHAT_API_BASE / VLLM_EMBED_API_BASE at a real inference server - see
docs/CREDENTIALS_AND_SETUP.md section 6. Everything else works without them.
'@ -ForegroundColor Green
