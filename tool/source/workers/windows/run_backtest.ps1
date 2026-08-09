param(
  [Parameter(Mandatory=$true)][string]$Terminal,
  [Parameter(Mandatory=$true)][string]$JobDir,
  [Parameter(Mandatory=$true)][string]$Config,
  [Parameter(Mandatory=$true)][string]$ExpectedReport,
  [string]$WorkerId = "win-worker"
)

$ErrorActionPreference = "Stop"
$configPath = Join-Path $JobDir $Config
$reportPath = Join-Path $JobDir $ExpectedReport

if (!(Test-Path $Terminal)) { throw "terminal64.exe not found: $Terminal" }
if (!(Test-Path $configPath)) { throw "tester config not found: $configPath" }

$proc = Start-Process -FilePath $Terminal -ArgumentList @("/portable", "/config:$configPath") -Wait -PassThru -NoNewWindow
$ok = ($proc.ExitCode -eq 0) -and (Test-Path $reportPath)

$result = [ordered]@{
  job_type = "backtest"
  status = $(if ($ok) { "passed" } else { "failed" })
  worker_id = $WorkerId
  exit_code = $proc.ExitCode
  tester_config = $configPath
  tester_report = $reportPath
  error = $(if ($ok) { $null } else { "MT5 terminal failed or tester report missing" })
}
$result | ConvertTo-Json -Depth 6 | Out-File -Encoding utf8 (Join-Path $JobDir "worker-result.raw.json")
if (!$ok) { exit 2 }
exit 0
