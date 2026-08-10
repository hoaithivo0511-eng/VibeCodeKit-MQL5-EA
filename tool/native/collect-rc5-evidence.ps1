[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$RepoRoot,
    [Parameter(Mandatory=$true)][string]$ProjectDir,
    [Parameter(Mandatory=$true)][string]$SourceMq5,
    [Parameter(Mandatory=$true)][string]$SetFile,
    [Parameter(Mandatory=$true)][string]$MetaEditor,
    [Parameter(Mandatory=$true)][string]$Terminal,
    [Parameter(Mandatory=$true)][string]$MetaEditorBuild,
    [Parameter(Mandatory=$true)][string]$TerminalBuild,
    [Parameter(Mandatory=$true)][string]$Symbol,
    [Parameter(Mandatory=$true)][string]$Period,
    [Parameter(Mandatory=$true)][string]$Timeframe,
    [Parameter(Mandatory=$true)][string]$StressReport,
    [Parameter(Mandatory=$true)][string]$ReviewReport,
    [Parameter(Mandatory=$true)][string]$AsyncFillReport,
    [Parameter(Mandatory=$true)][string]$RestartReport,
    [Parameter(Mandatory=$true)][string]$RunnerKey,
    [Parameter(Mandatory=$true)][string]$RunnerKeyId,
    [string]$Python = "python",
    [int]$TimeoutSec = 900
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-File([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label not found: $Path"
    }
}

$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$SourceMq5 = (Resolve-Path -LiteralPath $SourceMq5).Path
$SetFile = (Resolve-Path -LiteralPath $SetFile).Path
$MetaEditor = (Resolve-Path -LiteralPath $MetaEditor).Path
$Terminal = (Resolve-Path -LiteralPath $Terminal).Path
$StressReport = (Resolve-Path -LiteralPath $StressReport).Path
$ReviewReport = (Resolve-Path -LiteralPath $ReviewReport).Path
$AsyncFillReport = (Resolve-Path -LiteralPath $AsyncFillReport).Path
$RestartReport = (Resolve-Path -LiteralPath $RestartReport).Path
$RunnerKey = (Resolve-Path -LiteralPath $RunnerKey).Path

Assert-File $SourceMq5 "MQ5 source"
Assert-File $SetFile "SET file"
Assert-File $MetaEditor "MetaEditor64.exe"
Assert-File $Terminal "terminal64.exe"
Assert-File $StressReport "stress report"
Assert-File $ReviewReport "deep-review report"
Assert-File $AsyncFillReport "async-fill report"
Assert-File $RestartReport "restart-recovery report"
Assert-File $RunnerKey "runner private key"

if ($Period -notmatch '^(\d{4}\.\d{2}\.\d{2})-(\d{4}\.\d{2}\.\d{2})$') {
    throw "Period must be YYYY.MM.DD-YYYY.MM.DD"
}
$FromDate = $Matches[1]
$ToDate = $Matches[2]

$ProjectDir = [IO.Path]::GetFullPath($ProjectDir)
if ($ProjectDir.StartsWith((Join-Path $RepoRoot "docs"), [StringComparison]::OrdinalIgnoreCase)) {
    throw "ProjectDir must not be under docs/; release provenance treats docs as fixture space."
}
$TrustFile = Join-Path $ProjectDir "RELEASE-TRUST.yaml"
if (-not (Test-Path -LiteralPath $TrustFile -PathType Leaf)) {
    throw "Missing $TrustFile. Generate a native runner key and pin its fingerprint before execution."
}

$env:PYTHONPATH = (Join-Path $RepoRoot "tool\source\scripts")
$Scratch = Join-Path ([IO.Path]::GetTempPath()) ("vck-rc5-native-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $Scratch | Out-Null

try {
    $CompileOut = Join-Path $Scratch "compile"
    $CompileArgs = @(
        "-m", "vibecodekit_mql5.compile_runner",
        "--ea", $SourceMq5,
        "--out", $CompileOut,
        "--backend", "local-metaeditor",
        "--metaeditor", $MetaEditor
    )
    Write-Host "[Task10] Native MetaEditor compile"
    & $Python @CompileArgs
    if ($LASTEXITCODE -ne 0) { throw "MetaEditor compile runner failed with exit $LASTEXITCODE" }

    $CompileLog = Join-Path $CompileOut "compile.log"
    $CompiledEx5 = [IO.Path]::ChangeExtension($SourceMq5, ".ex5")
    Assert-File $CompileLog "compile log"
    Assert-File $CompiledEx5 "compiled EX5"

    $TesterReport = Join-Path $Scratch "tester-report.xml"
    $TesterIni = Join-Path $Scratch "tester.ini"
    $TesterStdout = Join-Path $Scratch "tester-result.json"
    $TesterArgs = @(
        "-m", "vibecodekit_mql5.tester_run",
        $CompiledEx5, $SetFile,
        "--symbol", $Symbol,
        "--period", $Period,
        "--tf", $Timeframe,
        "--report", $TesterReport,
        "--ini-out", $TesterIni,
        "--timeout", $TimeoutSec,
        "--terminal", $Terminal,
        "--no-wine"
    )
    Write-Host "[Task10] Native MT5 Strategy Tester"
    & $Python @TesterArgs | Tee-Object -FilePath $TesterStdout
    if ($LASTEXITCODE -ne 0) { throw "Strategy Tester runner failed with exit $LASTEXITCODE" }
    Assert-File $TesterReport "Strategy Tester XML report"
    Assert-File $TesterIni "tester.ini"

    $CompileCommand = "$Python " + (($CompileArgs | ForEach-Object { '"' + $_.Replace('"','\"') + '"' }) -join ' ')
    $TesterCommand = "$Python " + (($TesterArgs | ForEach-Object { '"' + $_.Replace('"','\"') + '"' }) -join ' ')
    $FinalizeScript = Join-Path $RepoRoot "scripts\release\native_evidence_collector.py"
    Assert-File $FinalizeScript "Task-10 release finalizer"

    $FinalizeArgs = @(
        $FinalizeScript,
        "--repo-root", $RepoRoot,
        "--project-dir", $ProjectDir,
        "--source-mq5", $SourceMq5,
        "--compile-log", $CompileLog,
        "--compiled-ex5", $CompiledEx5,
        "--tester-report", $TesterReport,
        "--tester-ini", $TesterIni,
        "--stress-report", $StressReport,
        "--review-report", $ReviewReport,
        "--async-fill-report", $AsyncFillReport,
        "--restart-report", $RestartReport,
        "--metaeditor-build", $MetaEditorBuild,
        "--terminal-build", $TerminalBuild,
        "--tester-symbol", $Symbol,
        "--tester-timeframe", $Timeframe,
        "--tester-from", $FromDate,
        "--tester-to", $ToDate,
        "--compile-command", $CompileCommand,
        "--tester-command", $TesterCommand,
        "--runner-key", $RunnerKey,
        "--runner-key-id", $RunnerKeyId
    )
    Write-Host "[Task10] Canonicalize + Ed25519 sign + verify"
    & $Python @FinalizeArgs
    if ($LASTEXITCODE -ne 0) { throw "Native evidence finalizer failed with exit $LASTEXITCODE" }

    Write-Host "[Task10] PASS locally. Evidence is at $ProjectDir"
    Write-Host "[Task10] Commit only evidence/public-key material; NEVER commit $RunnerKey"
}
finally {
    if (Test-Path -LiteralPath $Scratch) {
        Remove-Item -LiteralPath $Scratch -Recurse -Force
    }
}
