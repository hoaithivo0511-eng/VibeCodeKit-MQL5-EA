param(
  [Parameter(Mandatory=$true)][string]$MetaEditor,
  [Parameter(Mandatory=$true)][string]$JobDir,
  [Parameter(Mandatory=$true)][string]$EaFile,
  [string]$WorkerId = "win-worker"
)

$ErrorActionPreference = "Stop"
$eaPath = Join-Path $JobDir $EaFile
$logPath = Join-Path $JobDir "compile.log"
$ex5Path = [System.IO.Path]::ChangeExtension($eaPath, ".ex5")

if (!(Test-Path $MetaEditor)) { throw "MetaEditor not found: $MetaEditor" }
if (!(Test-Path $eaPath)) { throw "EA source not found: $eaPath" }

$proc = Start-Process -FilePath $MetaEditor -ArgumentList @("/compile:$eaPath", "/log:$logPath") -Wait -PassThru -NoNewWindow
$ok = ($proc.ExitCode -eq 0) -and (Test-Path $logPath) -and (Test-Path $ex5Path)

$result = [ordered]@{
  job_type = "compile"
  status = $(if ($ok) { "passed" } else { "failed" })
  worker_id = $WorkerId
  exit_code = $proc.ExitCode
  compile_log = $logPath
  ex5 = $ex5Path
  error = $(if ($ok) { $null } else { "MetaEditor failed or .ex5 missing" })
}
$result | ConvertTo-Json -Depth 6 | Out-File -Encoding utf8 (Join-Path $JobDir "worker-result.raw.json")
if (!$ok) { exit 2 }
exit 0
