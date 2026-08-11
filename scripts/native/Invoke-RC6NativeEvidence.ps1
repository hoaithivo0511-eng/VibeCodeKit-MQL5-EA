param(
  [Parameter(Mandatory=$true)][string]$EaIr,
  [Parameter(Mandatory=$true)][string]$SetFile,
  [Parameter(Mandatory=$true)][string]$MetaEditor,
  [Parameter(Mandatory=$true)][string]$Terminal,
  [Parameter(Mandatory=$true)][string]$RunnerKey,
  [Parameter(Mandatory=$true)][string]$KeyId,
  [Parameter(Mandatory=$true)][string]$PublicKeyB64,
  [Parameter(Mandatory=$true)][string]$RestartRecoveryReport,
  [Parameter(Mandatory=$true)][string]$RestartEvidenceDirectory,
  [string]$Symbol = "EURUSD",
  [string]$Timeframe = "H1",
  [string]$Period = "2025.01.01-2025.03.31",
  [string]$OutProject = "docs/release/v3.3.0rc6/native-evidence/project"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-File([string]$Path, [string]$Label) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "$Label not found: $Path" }
}

function Sha256([string]$Path) {
  return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Write-Utf8Json([object]$Value, [string]$Path, [int]$Depth = 12) {
  $json = $Value | ConvertTo-Json -Depth $Depth
  [System.IO.File]::WriteAllText($Path, $json + "`n", (New-Object System.Text.UTF8Encoding($false)))
}

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
Set-Location $Repo

$CandidateManifest = Join-Path $Repo "docs/release/v3.3.0rc6/RC6-CANDIDATE-MANIFEST.json"
$CandidateHashes = Join-Path $Repo "docs/release/v3.3.0rc6/RC6-ARTIFACTS.sha256"
$Wheel = Join-Path $Repo "tool/vibecodekit_mql5_ea-3.3.0rc6-py3-none-any.whl"
$RuntimeBundle = Join-Path $Repo "VibecodeKit-MQL5-v3.3.0rc6-runtime-candidate-bundle.zip"
$TrustFile = Join-Path $Repo "RELEASE-TRUST.yaml"

@($EaIr,$SetFile,$MetaEditor,$Terminal,$RunnerKey,$RestartRecoveryReport,$CandidateManifest,$CandidateHashes,$Wheel,$RuntimeBundle,$TrustFile) | ForEach-Object {
  Assert-File $_ "required input"
}
if (-not (Test-Path -LiteralPath $RestartEvidenceDirectory -PathType Container)) {
  throw "restart evidence directory not found: $RestartEvidenceDirectory"
}

$candidate = Get-Content -Raw -LiteralPath $CandidateManifest | ConvertFrom-Json
if ($candidate.kit_version -ne "3.3.0rc6") { throw "candidate kit_version mismatch" }
foreach ($artifact in $candidate.artifacts) {
  $path = Join-Path $Repo $artifact.path
  Assert-File $path "candidate artifact"
  if ((Sha256 $path) -ne ([string]$artifact.sha256).ToLowerInvariant()) {
    throw "candidate artifact hash mismatch: $($artifact.path)"
  }
}
$runtimeLine = Get-Content -LiteralPath $CandidateHashes | Where-Object { $_ -match "VibecodeKit-MQL5-v3.3.0rc6-runtime-candidate-bundle.zip$" } | Select-Object -First 1
if (-not $runtimeLine) { throw "runtime candidate hash record missing" }
$runtimeExpected = ($runtimeLine -split '\s+')[0].ToLowerInvariant()
if ((Sha256 $RuntimeBundle) -ne $runtimeExpected) { throw "runtime candidate bundle hash mismatch" }

$out = Join-Path $Repo $OutProject
if (Test-Path -LiteralPath $out) { Remove-Item -Recurse -Force -LiteralPath $out }
$inputDir = Join-Path $out "evidence/input"
$projectDir = Join-Path $inputDir "project"
$compileDir = Join-Path $out "evidence/compile"
$backtestDir = Join-Path $out "evidence/backtest"
$stressDir = Join-Path $out "evidence/stress"
$caseDir = Join-Path $stressDir "cases"
$reviewDir = Join-Path $out "evidence/review"
New-Item -ItemType Directory -Force -Path $inputDir,$projectDir,$compileDir,$backtestDir,$caseDir,$reviewDir | Out-Null
Copy-Item -LiteralPath $TrustFile -Destination (Join-Path $out "RELEASE-TRUST.yaml")
Copy-Item -LiteralPath $EaIr -Destination (Join-Path $inputDir "EA-IR.json")
Copy-Item -LiteralPath $SetFile -Destination (Join-Path $inputDir "test.set")

$venv = Join-Path $env:TEMP "vck-rc6-native-evidence"
if (Test-Path -LiteralPath $venv) { Remove-Item -Recurse -Force -LiteralPath $venv }
python -m venv $venv
$py = Join-Path $venv "Scripts/python.exe"
$pip = Join-Path $venv "Scripts/pip.exe"
& $pip install --disable-pip-version-check $Wheel
if ($LASTEXITCODE -ne 0) { throw "candidate wheel install failed" }
$installedVersion = (& $py -c "import importlib.metadata; print(importlib.metadata.version('vibecodekit-mql5-ea'))").Trim()
if ($installedVersion -ne [string]$candidate.kit_version) { throw "installed candidate version mismatch" }

$irBuilder = Join-Path $venv "Scripts/mql5-ir-build.exe"
$compileRunner = Join-Path $venv "Scripts/mql5-compile-runner.exe"
$testerRunner = Join-Path $venv "Scripts/mql5-tester-run.exe"
$reviewRunner = Join-Path $venv "Scripts/mql5-ea-senior-review.exe"
$runnerKeyCli = Join-Path $venv "Scripts/mql5-runner-key.exe"
@($irBuilder,$compileRunner,$testerRunner,$reviewRunner,$runnerKeyCli) | ForEach-Object { Assert-File $_ "candidate CLI" }

# The compiled EA can only come from the exact installed candidate wheel.
& $irBuilder --ir (Join-Path $inputDir "EA-IR.json") --out-dir $projectDir
if ($LASTEXITCODE -ne 0) { throw "candidate mql5-ir-build failed" }
$irBuildReport = Join-Path $projectDir "IR-BUILD-REPORT.json"
Assert-File $irBuildReport "IR build report"
$irBuild = Get-Content -Raw -LiteralPath $irBuildReport | ConvertFrom-Json
if (-not $irBuild.ok) { throw "IR build report is not ok" }
$generatedMain = (Resolve-Path ([string]$irBuild.generated_main)).Path
if (-not $generatedMain.StartsWith($projectDir, [StringComparison]::OrdinalIgnoreCase)) {
  throw "generated EA entrypoint escaped the candidate output directory"
}
Copy-Item -LiteralPath (Join-Path $inputDir "EA-IR.json") -Destination (Join-Path $projectDir "EA-IR.json")

$sourceFiles = @(Get-ChildItem -LiteralPath $projectDir -Recurse -File | Where-Object { $_.Extension -in @(".mq5", ".mqh") } | Sort-Object FullName)
if (-not ($sourceFiles | Where-Object { $_.Extension -eq ".mq5" })) { throw "generated project has no .mq5 entrypoint" }
if (-not ($sourceFiles | Where-Object { $_.Extension -eq ".mqh" })) { throw "generated project has no .mqh source" }
$sourceRecords = @()
foreach ($file in $sourceFiles) {
  $relative = $file.FullName.Substring($out.Length + 1).Replace("\", "/")
  $sourceRecords += [ordered]@{ path=$relative; size=$file.Length; sha256=(Sha256 $file.FullName) }
}
$entrypointRel = $generatedMain.Substring($out.Length + 1).Replace("\", "/")
$sourceManifest = [ordered]@{
  schema_version = "1.0"
  generated_by = "installed_candidate_wheel"
  candidate_source_tree_sha = [string]$candidate.source_tree_sha
  ea_entrypoint = $entrypointRel
  files = $sourceRecords
}
$sourceManifestPath = Join-Path $inputDir "source-manifest.json"
Write-Utf8Json $sourceManifest $sourceManifestPath 8

& $compileRunner --ea $generatedMain --out $compileDir --backend local-metaeditor --metaeditor $MetaEditor
if ($LASTEXITCODE -ne 0) { throw "trusted MetaEditor compile failed" }
$compileLog = Join-Path $compileDir "compile.log"
$ex5Source = [System.IO.Path]::ChangeExtension($generatedMain, ".ex5")
Assert-File $compileLog "MetaEditor compile log"
Assert-File $ex5Source "compiled EX5"
Copy-Item -LiteralPath $compileLog -Destination (Join-Path $compileDir "compile-log.txt")
Copy-Item -LiteralPath $ex5Source -Destination (Join-Path $compileDir "ea.ex5")

$testerReport = Join-Path $backtestDir "report.xml"
$testerJson = Join-Path $backtestDir "tester-result.json"
$testerIni = Join-Path $backtestDir "tester.ini"
$testerOutput = @(& $testerRunner (Join-Path $compileDir "ea.ex5") (Join-Path $inputDir "test.set") --symbol $Symbol --period $Period --tf $Timeframe --report $testerReport --ini-out $testerIni --terminal $Terminal --no-wine 2>&1)
$testerExitCode = $LASTEXITCODE
[System.IO.File]::WriteAllText($testerJson, ($testerOutput -join "`n") + "`n", (New-Object System.Text.UTF8Encoding($false)))
if ($testerExitCode -ne 0) { throw "trusted MT5 Strategy Tester failed" }
Assert-File $testerReport "Strategy Tester XML report"
Assert-File $testerIni "Strategy Tester configuration"
Assert-File $testerJson "Strategy Tester structured result"
$testerResult = Get-Content -Raw -LiteralPath $testerJson | ConvertFrom-Json
if ([int]$testerResult.total_trades -le 0) { throw "Strategy Tester produced zero trades" }

$requiredRestartCases = @("abrupt_terminal_kill","restart_reconcile","no_duplicate_order","legacy_v1_migration_restart")
$restart = Get-Content -Raw -LiteralPath $RestartRecoveryReport | ConvertFrom-Json
if ([string]$restart.source -notin @("actual_mt5_restart_recovery","remote_worker_mt5_restart_recovery")) {
  throw "restart recovery source is not trusted"
}
if ([string]$restart.candidate_source_tree_sha -ne [string]$candidate.source_tree_sha) {
  throw "restart recovery report is not bound to this RC6 candidate"
}
$caseMap = @{}
foreach ($case in $restart.restart_recovery_cases) { $caseMap[[string]$case.id] = $case }
foreach ($id in $requiredRestartCases) {
  if (-not $caseMap.ContainsKey($id) -or ([string]$caseMap[$id].status).ToUpperInvariant() -ne "PASS") {
    throw "restart recovery case $id is not PASS"
  }
  $sourceLog = Join-Path $RestartEvidenceDirectory "$id.log"
  Assert-File $sourceLog "restart case evidence"
  $destination = Join-Path $caseDir "$id.log"
  Copy-Item -LiteralPath $sourceLog -Destination $destination
  $caseMap[$id].evidence = "evidence/stress/cases/$id.log"
}
Write-Utf8Json $restart (Join-Path $stressDir "stress-matrix-report.json") 10

# Run the candidate's static reviewer over the exact generated project. Its
# expected pre-evidence release findings are excluded; every static critical
# or error finding remains a hard blocker.
$rawReviewPath = Join-Path $reviewDir "senior-review.raw.json"
& $reviewRunner --project $projectDir --out $rawReviewPath *> (Join-Path $reviewDir "senior-review.console.txt")
$rawReview = Get-Content -Raw -LiteralPath $rawReviewPath | ConvertFrom-Json
$staticBlocking = @($rawReview.issues | Where-Object { $_.category -ne "release" -and $_.severity -in @("critical", "error") })
if ($staticBlocking.Count -gt 0) { throw "candidate senior review found $($staticBlocking.Count) static blocker(s)" }
$normalizedFindings = @()
foreach ($issue in @($rawReview.issues | Where-Object { $_.category -ne "release" })) {
  $severity = switch ([string]$issue.severity) { "critical" { "P0" } "error" { "P1" } "warn" { "P2" } default { "P3" } }
  $normalizedFindings += [ordered]@{
    severity=$severity; status="ACCEPTED"; category=[string]$issue.category; summary=[string]$issue.title; evidence=[string]$issue.evidence
  }
}
$now = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
$deepReview = [ordered]@{
  schema_version = "1.0"
  status = "PASS"
  candidate_source_tree_sha = [string]$candidate.source_tree_sha
  project_source_manifest_sha256 = (Sha256 $sourceManifestPath)
  reviewer = "candidate-native-runner"
  reviewed_at_utc = $now
  release_blockers = @()
  findings = $normalizedFindings
}
Write-Utf8Json $deepReview (Join-Path $reviewDir "deep-review.json") 10

function Artifact([string]$Rel) {
  $path = Join-Path $out $Rel
  Assert-File $path "evidence artifact"
  return [ordered]@{ path=$Rel; exists=$true; sha256=(Sha256 $path) }
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
$artifactPaths = @(
  "evidence/compile/compile-log.txt",
  "evidence/compile/ea.ex5",
  "evidence/backtest/report.xml",
  "evidence/stress/stress-matrix-report.json",
  "evidence/review/deep-review.json",
  "evidence/input/EA-IR.json",
  "evidence/input/source-manifest.json",
  "evidence/input/test.set",
  "evidence/backtest/tester.ini",
  "evidence/backtest/tester-result.json"
)
$artifactPaths += @($sourceRecords | ForEach-Object { [string]$_.path })
$artifactPaths += @($requiredRestartCases | ForEach-Object { "evidence/stress/cases/$_.log" })
$artifacts = @($artifactPaths | Sort-Object -Unique | ForEach-Object { Artifact $_ })
$hostName = [Environment]::MachineName
$manifest = [ordered]@{
  schema_version = "2.1"
  release_eligible = $true
  summary = [ordered]@{ release_eligible=$true; compile_ok=$true; backtest_ok=$true; gates_ok=$true }
  compile = [ordered]@{
    ok=$true; source="actual_metaeditor"; command="mql5-compile-runner --backend local-metaeditor"; tool_version="MetaEditor/native"
    host=$hostName; recorded_at_utc=$now; returncode=0; candidate=$candidateBinding
    input_binding=[ordered]@{
      generated_by="installed_candidate_wheel"; ea_ir_sha256=(Sha256 (Join-Path $inputDir "EA-IR.json")); source_manifest_sha256=(Sha256 $sourceManifestPath)
      candidate_wheel_sha256=(Sha256 $Wheel); ea_entrypoint=$entrypointRel; entrypoint_sha256=(Sha256 $generatedMain)
    }
  }
  backtest = [ordered]@{
    ok=$true; source="actual_mt5_strategy_tester"; command="mql5-tester-run --no-wine"; tool_version="MetaTrader5/native"
    host=$hostName; recorded_at_utc=$now; returncode=0
    input_binding=[ordered]@{
      set_sha256=(Sha256 (Join-Path $inputDir "test.set")); tester_ini_sha256=(Sha256 $testerIni); symbol=$Symbol; timeframe=$Timeframe; period=$Period
    }
  }
  gates = [ordered]@{ ok=$true; restart_recovery=$true; review_present=$true }
  artifacts = $artifacts
}
$manifestPath = Join-Path $out "evidence/manifest.json"
Write-Utf8Json $manifest $manifestPath 14

$env:VCK_RUNNER_PUBLIC_KEY_B64 = $PublicKeyB64
& $runnerKeyCli sign $out --key $RunnerKey --key-id $KeyId
if ($LASTEXITCODE -ne 0) { throw "runner attestation signing failed" }
& $py -c "from vibecodekit_mql5.evidence_attestation import create_release_attestation,evaluate_release_evidence; import json,sys; p=sys.argv[1]; r=create_release_attestation(p,release_eligible=True); print(json.dumps(r.to_dict(),indent=2)); v=evaluate_release_evidence(p); print(json.dumps(v.to_dict(),indent=2)); raise SystemExit(0 if v.status=='PASS' else 4)" $out
if ($LASTEXITCODE -ne 0) { throw "native evidence attestation did not reach PASS" }
& $py (Join-Path $Repo "scripts/maintenance/verify_rc6_native_evidence.py") --native-project $out --require-pass
if ($LASTEXITCODE -ne 0) { throw "repository RC6 native verifier rejected evidence" }

Write-Host "RC6 native evidence PASS at $out"
