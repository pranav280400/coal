<#
.SYNOPSIS
  Download the local AI models into the `ollamadata` Docker volume (one-off, ~1.5 GB).

.DESCRIPTION
      docker compose --profile cpu-ai up -d ollama
      .\scripts\pull-models.ps1

  The model names must match infra/litellm/config.yaml. The embedding model must emit
  vectors of EMBEDDING_DIM (default 1024) - bge-m3 does.
#>

[CmdletBinding()]
param(
    [string]$ChatModel  = $(if ($env:OLLAMA_CHAT_MODEL)  { $env:OLLAMA_CHAT_MODEL }  else { "qwen2.5:3b-instruct" }),
    [string]$EmbedModel = $(if ($env:OLLAMA_EMBED_MODEL) { $env:OLLAMA_EMBED_MODEL } else { "bge-m3" })
)

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

$status = docker compose --profile cpu-ai ps ollama --format '{{.Status}}' 2>$null
if (-not ($status -match 'Up')) {
    Write-Host "Starting the ollama service first..." -ForegroundColor Cyan
    docker compose --profile cpu-ai up -d ollama
    Write-Host "Waiting for it to accept connections..."
    foreach ($i in 1..30) {
        docker compose --profile cpu-ai exec -T ollama ollama list *> $null
        if ($?) { break }
        Start-Sleep -Seconds 5
    }
}

foreach ($m in @($EmbedModel, $ChatModel)) {
    Write-Host "`n==> pulling $m" -ForegroundColor Cyan
    docker compose --profile cpu-ai exec -T ollama ollama pull $m
    if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: failed to pull $m" -ForegroundColor Red; exit 1 }
}

Write-Host ""
docker compose --profile cpu-ai exec -T ollama ollama list

Write-Host @'

Models are cached in the `coalminegov_ollamadata` volume, so this is a one-time download.

Next:
    docker compose restart litellm api worker consumers
    docker compose exec api python -m app.cli reindex-knowledge    # build the RAG index

Then open http://localhost:3000/assistant and ask a question.
'@ -ForegroundColor Green
