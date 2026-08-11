param(
  [Parameter(Mandatory=$true)][string]$EaPath,
  [Parameter(Mandatory=$true)][string]$SetFile,
  [Parameter(Mandatory=$true)][string]$MetaEditor,
  [Parameter(Mandatory=$true)][string]$Terminal,
  [Parameter(Mandatory=$true)][string]$RunnerKey,
  [Parameter(Mandatory=$true)][string]$KeyId,
  [Parameter(Mandatory=$true)][string]$PublicKeyB64,
  [Parameter(Mandatory=$true)][string]$RestartRecoveryReport,
  [Parameter(Mandatory=$true)][string]$DeepReviewReport,
  [string]$Symbol = "EURUSD",
  [string]$Timeframe = "H1",
  [string]$Period = "2025.01.01-2025.03.31",
  [string]$OutProject = "docs/release/v3.3.0rc5/native-evidence/project"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-File([string]$Path, [string]$Label) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    throw "$Label not found: $Path"
  }
}

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
Set-Location $Repo

$CandidateManifest = Join-Path $Repo "docs/release/v3.3.0rc5/RC5-CANDIDATE-MANIFEST.json"
$CandidateHashes = Join-Path $Repo "docs/release/v3.3.0rc5/RC5-ARTIFACTS.sha256"
$Wheel = Join-Path $Repo "tool/vibecodekit_mql5_ea-3.3.0rc5-py3-none-any.whl"
$RuntimeBundle = Join-Path $Repo "VibecodeKit-MQL5-v3.3.0rc5-runtime-candidate-bundle.zip"
$TrustFile = Join-Path $Repo "RELEASE-TRUST.yaml"

@($EaPath,$SetFile,$MetaEditor,$Terminal,$RunnerKey,$RestartRecoveryReport,$DeepReviewReport,$CandidateManifest,$CandidateHashes,$Wheel,$RuntimeBundle,$TrustFile) | ForEach-Object {
  Assert-File $_ "required input"
}

$candidate = Get-Content -Raw -LiteralPath $CandidateManifest | ConvertFrom-Json
if ($candidate.kit_version -ne "3.3.0rc5") { throw "candidate kit_version mismatch" }
foreach ($artifact in $candidate.artifacts) {
  $path = Join-Path $Repo $artifact.path
  Assert-File $path "candidate artifact"
  $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
  if ($actual -ne ([string]$artifact.sha256).ToLowerInvariant()) {
    throw "candidate artifact hash mismatch: $($artifact.path)"
  }
}
$runtimeLine = Get-Content -LiteralPath $CandidateHashes | Where-Object { $_ -match "VibecodeKit-MQL5-v3.3.0rc5-runtime-candidate-bundle.zip$" } | Select-Object -First 1
if (-not $runtimeLine) { throw "runtime candidate hash record missing" }
$runtimeExpected = ($runtimeLine -split '\s+')[0].ToLowerInvariant()
$runtimeActual = (Get-FileHash -Algorithm SHA256 -LiteralPath $RuntimeBundle).Hash.ToLowerInvariant()
if ($runtimeExpected -ne $runtimeActual) { throw "runtime candidate bundle hash mismatch" }

$out = Join-Path $Repo $OutProject
if (Test-Path -LiteralPath $out) { Remove-Item -Recurse -Force -LiteralPath $out }
$compileDir = Join-Path $out "evidence/compile"
$backtestDir = Join-Path $out "evidence/backtest"
$stressDir = Join-Path $out "evidence/stress"
$reviewDir = Join-Path $out "evidence/review"
New-Item -ItemType Directory -Force -Path $compileDir,$backtestDir,$stressDir,$reviewDir | Out-Null
Copy-Item -LiteralPath $TrustFile -Destination (Join-Path $out "RELEASE-TRUST.yaml")

$venv = Join-Path $env:TEMP "vck-rc5-native-evidence"
if (Test-Path -LiteralPath $venv) { Remove-Item -Recurse -Force -LiteralPath $venv }
python -m venv $venv
$py = Join-Path $venv "Scripts/python.exe"
$pip = Join-Path $venv "Scripts/pip.exe"
& $pip install --disable-pip-version-check $Wheel
if ($LASTEXITCODE -ne 0) { throw "candidate wheel install failed" }

$compileRunner = Join-Path $venv "Scripts/mql5-compile-runner.exe"
$testerRunner = Join-Path $venv "Scripts/mql5-tester-run.exe"
$runnerKeyCli = Join-Path $venv "Scripts/mql5-runner-key.exe"
Assert-File $compileRunner "mql5-compile-runner"
Assert-File $testerRunner "mql5-tester-run"
Assert-File $runnerKeyCli "mql5-runner-key"

& $compileRunner --ea $EaPath --out $compileDir --backend local-metaeditor --metaeditor $MetaEditor
if ($LASTEXITCODE -ne 0) { throw "trusted MetaEditor compile failed" }
$compileLog = Join-Path $compileDir "compile.log"
$ex5Source = [System.IO.Path]::ChangeExtension((Resolve-Path $EaPath).Path, ".ex5")
Assert-File $compileLog "MetaEditor compile log"
Assert-File $ex5Source "compiled EX5"
Copy-Item -LiteralPath $compileLog -Destination (Join-Path $compileDir "compile-log.txt")
Copy-Item -LiteralPath $ex5Source -Destination (Join-Path $compileDir "ea.ex5")

$testerReport = Join-Path $backtestDir "report.xml"
$testerJson = Join-Path $backtestDir "tester-result.json"
& $testerRunner (Join-Path $compileDir "ea.ex5") $SetFile --symbol $Symbol --period $Period --tf $Timeframe --report $testerReport --ini-out (Join-Path $backtestDir "tester.ini") --terminal $Terminal --no-wine *> $testerJson
if ($LASTEXITCODE -ne 0) { throw "trusted MT5 Strategy Tester failed" }
Assert-File $testerReport "Strategy Tester XML report"

Copy-Item -LiteralPath $RestartRecoveryReport -Destination (Join-Path $stressDir "stress-matrix-report.json")
Copy-Item -LiteralPath $DeepReviewReport -Destination (Join-Path $reviewDir "deep-review.json")

$requiredRestartCases = @("abrupt_terminal_kill","restart_reconcile","no_duplicate_order","legacy_v1_migration_restart")
$restart = Get-Content -Raw -LiteralPath (Join-Path $stressDir "stress-matrix-report.json") | ConvertFrom-Json
$caseMap = @{}
foreach ($case in $restart.restart_recovery_cases) { $caseMap[[string]$case.id] = ([string]$case.status).ToUpperInvariant() }
foreach ($id in $requiredRestartCases) {
  if (-not $caseMap.ContainsKey($id) -or $caseMap[$id] -ne "PASS") { throw "restart recovery case $id is not PASS" }
}

function Artifact([string]$Rel) {
  $path = Join-Path $out $Rel
  Assert-File $path "evidence artifact"
  return [ordered]@{ path=$Rel; exists=$true; sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant() }
}

$artifactBinding = [ordered]@{}
foreach ($artifact in $candidate.artifacts) { $artifactBinding[[string]$artifact.path] = [string]$artifact.sha256 }
$candidateBinding = [ordered]@{
  kit_version = [string]$candidate.kit_version
  build_input_commit = [string]$candidate.build_input_commit
  source_tree_sha = [string]$candidate.source_tree_sha
  artifacts = $artifactBinding
  runtime_bundle_sha256 = $runtimeExpected
}
$now = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
$hostName = [Environment]::MachineName
$manifest = [ordered]@{
  schema_version = "2.0"
  release_eligible = $true
  summary = [ordered]@{ release_eligible=$true; compile_ok=$true; backtest_ok=$true; gates_ok=$true }
  compile = [ordered]@{
    ok = $true
    source = "actual_metaeditor"
    command = "mql5-compile-runner --backend local-metaeditor"
    tool_version = "MetaEditor/native"
    host = $hostName
    recorded_at_utc = $now
    returncode = 0
    candidate = $candidateBinding
  }
  backtest = [ordered]@{
    ok = $true
    source = "actual_mt5_strategy_tester"
    command = "mql5-tester-run --no-wine"
    tool_version = "MetaTrader5/native"
    host = $hostName
    recorded_at_utc = $now
    returncode = 0
  }
  gates = [ordered]@{ ok=$true; restart_recovery=$true; review_present=$true }
  artifacts = @(
    (Artifact "evidence/compile/compile-log.txt"),
    (Artifact "evidence/compile/ea.ex5"),
    (Artifact "evidence/backtest/report.xml"),
    (Artifact "evidence/stress/stress-matrix-report.json"),
    (Artifact "evidence/review/deep-review.json")
  )
}
$manifestPath = Join-Path $out "evidence/manifest.json"
$manifest | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 -LiteralPath $manifestPath

$env:VCK_RUNNER_PUBLIC_KEY_B64 = $PublicKeyB64
& $runnerKeyCli sign $out --key $RunnerKey --key-id $KeyId
if ($LASTEXITCODE -ne 0) { throw "runner attestation signing failed" }

& $py -c "from vibecodekit_mql5.evidence_attestation import create_release_attestation,evaluate_release_evidence; import json,sys; p=sys.argv[1]; r=create_release_attestation(p, release_eligible=True); print(json.dumps(r.to_dict(),indent=2)); v=evaluate_release_evidence(p); print(json.dumps(v.to_dict(),indent=2)); raise SystemExit(0 if v.status=='PASS' else 4)" $out
if ($LASTEXITCODE -ne 0) { throw "native evidence attestation did not reach PASS" }

& $py (Join-Path $Repo "scripts/maintenance/verify_rc5_native_evidence.py") --native-project $out --require-pass
if ($LASTEXITCODE -ne 0) { throw "repository Task 10 verifier rejected native evidence" }

Write-Host "Task 10 native evidence PASS at $out"
