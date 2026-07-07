# Pull BMV AI models into Docker (production ollama volume)
# Requires: Docker Desktop running, ~15 GB free disk for images + models

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot + "\.."

if (-not (Test-Path ".env")) {
    Write-Host "Copy .env.prod.example to .env and set DOMAIN / ACME_EMAIL (localhost placeholders are fine locally)."
    exit 1
}

Write-Host "Starting Ollama container..."
docker compose -f docker-compose.prod.yml up -d ollama

Write-Host "Waiting for Ollama health..."
$ok = $false
for ($i = 1; $i -le 60; $i++) {
    $h = docker inspect bmv-ollama --format "{{.State.Health.Status}}" 2>$null
    if ($h -eq "healthy") { $ok = $true; break }
    Start-Sleep 5
}
if (-not $ok) { Write-Warning "Ollama not healthy yet — init may still work after a minute." }

Write-Host "Pulling llama3.1:8b, llama3.2-vision, qwen2.5-coder:7b (this takes a while)..."
docker compose -f docker-compose.prod.yml --profile init run --rm ollama-init

Write-Host "`nDone. Models in volume: buildmyversion-prod_ollama-models"
docker compose -f docker-compose.prod.yml exec ollama ollama list
