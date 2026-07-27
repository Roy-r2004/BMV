# Preview Generator v2 release gate — deterministic tests only.
# Usage: pwsh scripts/verify-preview-v2-release.ps1 [-Mode default|full|production-readiness]
param(
  [ValidateSet("default", "full", "production-readiness")]
  [string]$Mode = "default"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Backend = Join-Path $Root "backend"
$ProductionReadinessRoot = Join-Path $Backend ".runtime\production-readiness"
$ProductionReadinessEnvNames = @(
  "APP_ENV",
  "PREVIEW_GENERATOR_V2",
  "BMV_READINESS_RESTART_RESUME_PASSED",
  "V2_CANDIDATE_COMPONENT_MODEL",
  "V2_CANDIDATE_PAGE_MODEL",
  "APPSPEC_FALLBACK_ENABLED",
  "V2_PHASE7_ROLLOUT_ENABLED",
  "V2_PHASE7_PROMOTE_ENABLED",
  "V2_PHASE7_PERCENT_SERVE_ENABLED",
  "V2_PHASE7_ROLLOUT_PERCENT",
  "V2_RUNTIME_VALIDATION_ENABLED",
  "V2_VISUAL_EVALUATION_ENABLED"
)
Set-Location $Backend
$Failed = 0

function Section([string]$Name) {
  Write-Host ""
  Write-Host "==> $Name"
}

function Invoke-GatePytest([string]$Label, [string[]]$PytestArgs) {
  Section $Label
  & python -m pytest @PytestArgs
  if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL $Label"
    $script:Failed = 1
  } else {
    Write-Host "OK  $Label"
  }
}

function Invoke-ReleaseGateCommon {
  Section "compileall"
  & python -m compileall -q app
  if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL compileall"
    $script:Failed = 1
  } else {
    Write-Host "OK  compileall"
  }

  Section "git diff --check"
  & git -C $Root diff --check
  if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL git diff --check"
    $script:Failed = 1
  } else {
    Write-Host "OK  git diff --check"
  }

  Invoke-GatePytest "failure audit harness + known failures + fuzz" @(
    "tests/preview_audit/test_failure_injection_harness.py",
    "tests/preview_audit/test_known_failure_replay.py",
    "tests/preview_audit/test_contract_fuzzing.py",
    "tests/preview_audit/test_phase4_preflight_gap.py",
    "-q", "--tb=line"
  )

  Invoke-GatePytest "business-component usage" @(
    "tests/candidate_generation/test_business_component_usage.py", "-q", "--tb=line"
  )
  Invoke-GatePytest "Phase 3B candidates" @(
    "tests/candidate_generation/test_phase3b_candidate_generation.py", "-q", "--tb=line"
  )
  Invoke-GatePytest "composition contract" @("tests/composition_contract", "-q", "--tb=line")
  Invoke-GatePytest "AppSpec graph repair" @("tests/appspec/test_graph_repair.py", "-q", "--tb=line")
  Invoke-GatePytest "Tier1 closure heal" @("tests/preview_contract/test_tier1_closure_heal.py", "-q", "--tb=line")
  Invoke-GatePytest "commercial Expanded Preview + migration readiness" @(
    "tests/commercial/test_expanded_preview_workflow.py",
    "tests/commercial/test_migration_startup_safety.py",
    "-q", "--tb=line"
  )

  if ($Mode -eq "full" -or $env:BMV_V2_MATRIX -eq "1") {
    Invoke-GatePytest "local simulation matrix (provider doubles)" @(
      "tests/preview_audit/test_local_simulation_matrix.py", "-q", "--tb=line"
    )
  } else {
    Section "local simulation matrix (skipped; use -Mode full or BMV_V2_MATRIX=1)"
  }
}

function Require-Env([string]$Name) {
  $entry = Get-Item -Path "Env:$Name" -ErrorAction SilentlyContinue
  if ($null -eq $entry -or [string]::IsNullOrWhiteSpace([string]$entry.Value)) {
    throw "Required environment variable missing: $Name"
  }
}

function Get-EnvSnapshot([string[]]$Names) {
  $snapshot = @()
  foreach ($name in $Names) {
    $entry = Get-Item -Path "Env:$name" -ErrorAction SilentlyContinue
    $snapshot += [pscustomobject]@{
      Name = $name
      Present = ($null -ne $entry)
      Value = $(if ($null -ne $entry) { [string]$entry.Value } else { $null })
    }
  }
  return ,$snapshot
}

function Restore-EnvSnapshot($Snapshot) {
  foreach ($item in @($Snapshot)) {
    $name = [string]$item.Name
    if ($item.Present) {
      Set-Item -Path "Env:$name" -Value ([string]$item.Value)
    } else {
      Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
    }
  }
}

function Get-ObjectProperty($InputObject, [string]$Name, $Default = $null) {
  if ($null -eq $InputObject) {
    return $Default
  }
  if ($InputObject -is [System.Collections.IDictionary]) {
    if ($InputObject.Contains($Name)) {
      return $InputObject[$Name]
    }
    return $Default
  }
  $property = $InputObject.PSObject.Properties[$Name]
  if ($null -ne $property) {
    return $property.Value
  }
  return $Default
}

function Get-ObjectChild($InputObject, [string]$Name) {
  $child = Get-ObjectProperty -InputObject $InputObject -Name $Name -Default $null
  if ($null -eq $child) {
    return [pscustomobject]@{}
  }
  return $child
}

function Get-ValidatedPreflightSha([string]$ReportPath) {
  $report = Get-Content -LiteralPath $ReportPath -Raw | ConvertFrom-Json
  $requiredSections = @(
    "configuration",
    "deterministic_suites",
    "prompt_variants",
    "model_preflights",
    "phase3a",
    "provider_calls",
    "candidate_generation",
    "call_budgets",
    "checkpoints",
    "generated_code_validation",
    "restart_resume"
  )
  $failures = @(Get-ObjectProperty -InputObject $report -Name "failures" -Default @())
  if ($failures.Count -gt 0) {
    throw "Host preflight report recorded failures."
  }
  foreach ($section in $requiredSections) {
    $payload = Get-ObjectChild -InputObject $report -Name $section
    $status = [string](Get-ObjectProperty -InputObject $payload -Name "status" -Default "")
    if ($status.ToLowerInvariant() -ne "pass") {
      throw "Host preflight section did not pass: $section"
    }
  }
  $dockerEnvironment = Get-ObjectChild -InputObject $report -Name "docker_environment"
  $dockerStatus = [string](Get-ObjectProperty -InputObject $dockerEnvironment -Name "status" -Default "")
  if ($dockerStatus.ToLowerInvariant() -ne "deferred_to_production_image") {
    throw "Host preflight docker_environment must be deferred_to_production_image."
  }
  if ((Get-ObjectProperty -InputObject $dockerEnvironment -Name "host_environment" -Default $false) -ne $true) {
    throw "Host preflight docker_environment.host_environment must be true."
  }
  if ((Get-ObjectProperty -InputObject $dockerEnvironment -Name "production_image_required" -Default $false) -ne $true) {
    throw "Host preflight docker_environment.production_image_required must be true."
  }
  $restartResume = Get-ObjectChild -InputObject $report -Name "restart_resume"
  if ([string](Get-ObjectProperty -InputObject $restartResume -Name "source" -Default "") -ne "release_gate_deterministic_suite") {
    throw "Host preflight restart_resume source must be release_gate_deterministic_suite."
  }
  if ([string](Get-ObjectProperty -InputObject $report -Name "required_next_action" -Default "") -ne "run_real_http_flow") {
    throw "Host preflight report required_next_action must be run_real_http_flow."
  }
  $artifacts = Get-ObjectChild -InputObject $report -Name "artifacts"
  $sha = [string](Get-ObjectProperty -InputObject $artifacts -Name "preflight_report_sha256" -Default "")
  if ($sha.Length -ne 64) {
    throw "Host preflight report missing bound preflight_report_sha256."
  }
  return $sha
}

function Invoke-DockerCompose([string[]]$Args) {
  & docker compose -p $script:ComposeProjectName -f $script:ComposeFile -f $script:ComposeOverrideFile @Args
}

function Wait-ContainerHealthy([string]$ContainerId) {
  $deadline = (Get-Date).AddMinutes(4)
  while ((Get-Date) -lt $deadline) {
    $status = (& docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" $ContainerId).Trim()
    if ($LASTEXITCODE -ne 0) {
      throw "Failed to inspect container health."
    }
    if ($status -eq "healthy") {
      return
    }
    if ($status -in @("unhealthy", "exited", "dead")) {
      throw "Container health failed with status: $status"
    }
    Start-Sleep -Seconds 2
  }
  throw "Container did not become healthy before timeout."
}

function Save-ComposeFailureArtifacts([string]$ArtifactRoot, [string]$LogPath) {
  try {
    # Preserve docker compose logs without automatic teardown on failure.
    Invoke-DockerCompose @("logs", "--no-color", "app") | Out-File -LiteralPath $LogPath -Encoding utf8
  } catch {
  }
  Write-Host "Artifacts preserved at $ArtifactRoot"
  Write-Host "No automatic teardown on failure."
}

function Invoke-ProductionReadinessMode {
  Invoke-GatePytest "#33-36 candidate reliability matrix" @(
    "tests/candidate_generation/test_request33_provider_reliability.py",
    "tests/candidate_generation/test_request34_context_overflow.py",
    "tests/candidate_generation/test_request35_pages_model.py",
    "tests/candidate_generation/test_request36_component_model.py",
    "-q", "--tb=line"
  )

  Remove-Item -Path "Env:BMV_READINESS_RESTART_RESUME_PASSED" -ErrorAction SilentlyContinue
  Section "candidate resume caps and repair"
  & python -m pytest @(
    "tests/candidate_generation/test_candidate_resume.py",
    "tests/composition_contract/test_phase3a_call_budget.py",
    "tests/candidate_generation/test_phase3b_candidate_generation.py",
    "-q", "--tb=line"
  )
  if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL candidate resume caps and repair"
    $script:Failed = 1
    Remove-Item -Path "Env:BMV_READINESS_RESTART_RESUME_PASSED" -ErrorAction SilentlyContinue
  } else {
    $env:BMV_READINESS_RESTART_RESUME_PASSED = "1"
    Write-Host "OK  candidate resume caps and repair"
  }

  Invoke-GatePytest "response parser OpenRouter matrix" @(
    "tests/infrastructure/ai_providers/test_response_parser.py",
    "tests/infrastructure/ai_providers/test_openrouter_error_matrix.py",
    "-q", "--tb=line"
  )

  Invoke-GatePytest "AppSpec fallback safety" @(
    "tests/preview_contract/test_appspec_v2_policy.py",
    "-q", "--tb=line"
  )

  Invoke-GatePytest "customer response security admin 401" @(
    "tests/security/test_customer_preview_responses.py",
    "tests/preview_audit/test_preview_v2_production_readiness_default_checks.py",
    "tests/preview_audit/test_preview_v2_production_readiness_driver.py",
    "-q", "--tb=line"
  )

  Invoke-GatePytest "Phase7 off tests" @(
    "tests/rollout/test_phase7a_flags.py",
    "-q", "--tb=line"
  )

  Invoke-GatePytest "Expanded Preview no auto start" @(
    "tests/commercial/test_staging_flags_and_no_auto_tier2.py",
    "-q", "--tb=line"
  )

  Invoke-GatePytest "real Phase4 and Phase5 suites" @(
    "tests/runtime_validation/test_phase4_runtime_validation.py",
    "tests/visual_evaluation/test_phase5_visual_evaluation.py",
    "-q", "--tb=line"
  )

  Invoke-ReleaseGateCommon

  Section "summary"
  if ($Failed -ne 0) {
    Write-Host "RELEASE GATE FAILED"
    Write-Host "production-readiness stopped before Docker and real flow."
    exit 1
  }

  New-Item -ItemType Directory -Force -Path $ProductionReadinessRoot | Out-Null
  $runId = [Guid]::NewGuid().ToString("N")
  $artifactRoot = Join-Path $ProductionReadinessRoot $runId
  $hostPreflightReport = Join-Path $artifactRoot "host-preflight.json"
  $realFlowReport = Join-Path $artifactRoot "real-http-report.json"
  $composeLogs = Join-Path $artifactRoot "docker-compose.logs.txt"
  $script:ComposeOverrideFile = Join-Path $artifactRoot "docker-compose.production-readiness.override.yml"
  $script:ComposeFile = Join-Path $Root "docker-compose.coolify.yml"
  $script:ComposeProjectName = "bmv-production-readiness-$runId"
  $volumeName = "bmv-production-readiness-$runId"
  $containerDataRoot = "/app/data/production-readiness/$runId"
  $containerPreflightReport = "$containerDataRoot/host-preflight.json"
  $containerRealFlowReport = "$containerDataRoot/real-http-report.json"
    $containerAccessTokenFile = "$containerDataRoot/customer-access.token"
  $envSnapshot = Get-EnvSnapshot -Names $ProductionReadinessEnvNames
  New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null
  try {
    Require-Env "ADMIN_PASSWORD"
    Require-Env "OPENROUTER_API_KEY"

    $env:APP_ENV = "production"
    $env:PREVIEW_GENERATOR_V2 = "true"
    $env:V2_CANDIDATE_COMPONENT_MODEL = "google/gemini-2.5-flash"
    $env:V2_CANDIDATE_PAGE_MODEL = "google/gemini-2.5-flash"
    $env:APPSPEC_FALLBACK_ENABLED = "false"
    $env:V2_PHASE7_ROLLOUT_ENABLED = "false"
    $env:V2_PHASE7_PROMOTE_ENABLED = "false"
    $env:V2_PHASE7_PERCENT_SERVE_ENABLED = "false"
    $env:V2_PHASE7_ROLLOUT_PERCENT = "0"
    $env:V2_RUNTIME_VALIDATION_ENABLED = "true"
    $env:V2_VISUAL_EVALUATION_ENABLED = "true"

    @"
services:
  app:
    ports: []
volumes:
  bmv-persistent-data:
    name: $volumeName
"@ | Out-File -LiteralPath $script:ComposeOverrideFile -Encoding utf8

    Section "host preflight report"
    & python scripts/cli/preview_v2_production_readiness.py `
      --preflight-only `
      --report-path $hostPreflightReport
    $preflightExit = $LASTEXITCODE
    if ($preflightExit -eq 0) {
      throw "Host preflight unexpectedly returned success; real flow should still be pending."
    }
    $preflightReportSha256 = Get-ValidatedPreflightSha -ReportPath $hostPreflightReport
    Write-Host "OK  host preflight report"

    Section "build exact Dockerfile.app image"
    Invoke-DockerCompose @("build", "app") | Out-Null
    if ($LASTEXITCODE -ne 0) {
      throw "docker compose build failed."
    }

    Section "docker start app"
    Invoke-DockerCompose @("up", "-d", "app") | Out-Null
    if ($LASTEXITCODE -ne 0) {
      throw "docker compose up failed."
    }

    $containerId = (Invoke-DockerCompose @("ps", "-q", "app") | Select-Object -Last 1).Trim()
    if ([string]::IsNullOrWhiteSpace($containerId)) {
      throw "Could not resolve the compose app container id."
    }

    Section "wait for app health"
    Wait-ContainerHealthy -ContainerId $containerId

    Section "copy preflight report into container"
    Invoke-DockerCompose @("exec", "-T", "app", "mkdir", "-p", $containerDataRoot) | Out-Null
    if ($LASTEXITCODE -ne 0) {
      throw "Failed to create container artifact directory."
    }
    & docker cp $hostPreflightReport "${containerId}:${containerPreflightReport}"
    if ($LASTEXITCODE -ne 0) {
      throw "Failed to copy host preflight report into container."
    }

    Section "container real HTTP flow"
    Invoke-DockerCompose @(
      "exec", "-T", "app",
      "python", "scripts/cli/preview_v2_production_readiness.py",
      "--run-real-http",
      "--preflight-report", $containerPreflightReport,
      "--preflight-report-sha256", $preflightReportSha256,
      "--resume-access-token-file", $containerAccessTokenFile,
      "--report-path", $containerRealFlowReport
    ) | Out-Null
    $realExit = $LASTEXITCODE

    & docker cp "${containerId}:${containerRealFlowReport}" $realFlowReport 2>$null
    if ($realExit -ne 0) {
      Save-ComposeFailureArtifacts -ArtifactRoot $artifactRoot -LogPath $composeLogs
      exit $realExit
    }
    if (-not (Test-Path -LiteralPath $realFlowReport)) {
      Save-ComposeFailureArtifacts -ArtifactRoot $artifactRoot -LogPath $composeLogs
      throw "Real flow report was not copied back to host."
    }

    Section "teardown success container"
    Invoke-DockerCompose @("down", "-v", "--remove-orphans") | Out-Null
    if ($LASTEXITCODE -ne 0) {
      throw "docker compose down failed after success."
    }
    Section "summary"
    Write-Host "RELEASE GATE PASSED (mode=$Mode)"
    exit 0
  } catch {
    Save-ComposeFailureArtifacts -ArtifactRoot $artifactRoot -LogPath $composeLogs
    throw
  } finally {
    Restore-EnvSnapshot -Snapshot $envSnapshot
  }
}

if ($Mode -eq "production-readiness") {
  Invoke-ProductionReadinessMode
  exit 1
}

Invoke-ReleaseGateCommon

Section "summary"
if ($Failed -ne 0) {
  Write-Host "RELEASE GATE FAILED"
  exit 1
}
Write-Host "RELEASE GATE PASSED (mode=$Mode)"
exit 0
