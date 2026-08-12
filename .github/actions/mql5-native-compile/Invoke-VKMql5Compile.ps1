param(
  [Parameter(Mandatory=$true)][string]$Target,
  [string]$TargetsJson = "",
  [string]$ProjectRoot = ".",
  [string]$EvidenceDir = "evidence/compile",
  [string]$MetaEditor = "",
  [string]$InstallerUrl = "",
  [string]$InstallerSha256 = "",
  [string]$GitHubToken = "",
  [string]$ExpectedCommit = "",
  [ValidateSet("auto","always","never")][string]$WarmStdlib = "auto",
  [int]$TimeoutSeconds = 180,
  [string]$KitVersion = "3.3.0rc7"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Sha256([string]$Path) {
  return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Write-Utf8Json([object]$Value, [string]$Path, [int]$Depth = 16) {
  $parent = Split-Path -Parent $Path
  if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
  $json = $Value | ConvertTo-Json -Depth $Depth
  [System.IO.File]::WriteAllText($Path, $json + "`n", (New-Object System.Text.UTF8Encoding($false)))
}

function Read-TextAnyEncoding([string]$Path) {
  $bytes = [System.IO.File]::ReadAllBytes($Path)
  if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xff -and $bytes[1] -eq 0xfe) {
    return [System.Text.Encoding]::Unicode.GetString($bytes).TrimStart([char]0xfeff)
  }
  if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xfe -and $bytes[1] -eq 0xff) {
    return [System.Text.Encoding]::BigEndianUnicode.GetString($bytes).TrimStart([char]0xfeff)
  }
  if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xef -and $bytes[1] -eq 0xbb -and $bytes[2] -eq 0xbf) {
    return [System.Text.Encoding]::UTF8.GetString($bytes).TrimStart([char]0xfeff)
  }
  try {
    $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
    return $strictUtf8.GetString($bytes)
  } catch {
    return [System.Text.Encoding]::Default.GetString($bytes)
  }
}

function Detect-Encoding([string]$Path) {
  $bytes = [System.IO.File]::ReadAllBytes($Path)
  if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xff -and $bytes[1] -eq 0xfe) { return "utf-16-le-bom" }
  if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xfe -and $bytes[1] -eq 0xff) { return "utf-16-be-bom" }
  if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xef -and $bytes[1] -eq 0xbb -and $bytes[2] -eq 0xbf) { return "utf-8-bom" }
  try {
    $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
    [void]$strictUtf8.GetString($bytes)
    return "utf-8"
  } catch {
    return "system-ansi"
  }
}

function Assert-SafeHttpsUrl([string]$Url) {
  $uri = [Uri]$Url
  if ($uri.Scheme -ne "https") { throw "TOOLCHAIN_INSTALL_FAILED: installer URL must use https" }
  $hostName = $uri.DnsSafeHost.ToLowerInvariant()
  if ($hostName -in @("localhost","0.0.0.0","::1") -or $hostName.StartsWith("127.") -or $hostName.StartsWith("169.254.")) {
    throw "TOOLCHAIN_INSTALL_FAILED: installer URL resolves to a forbidden local/link-local host name"
  }
}

function Resolve-MetaEditor([string]$Override, [string]$Installer, [string]$ExpectedInstallerSha) {
  if ($Override) {
    $resolved = Resolve-Path -LiteralPath $Override -ErrorAction SilentlyContinue
    if ($resolved) {
      return [ordered]@{ path=$resolved.Path; installer_sha256=""; installed=$false }
    }
    throw "TOOLCHAIN_INSTALL_FAILED: MetaEditor override not found: $Override"
  }
  if (-not $Installer) { throw "TOOLCHAIN_INSTALL_FAILED: MetaEditor path or installer-url is required" }
  Assert-SafeHttpsUrl $Installer
  $installerPath = Join-Path $env:RUNNER_TEMP "vkmql-mt5setup.exe"
  Invoke-WebRequest -Uri $Installer -OutFile $installerPath -UseBasicParsing
  $actualSha = Sha256 $installerPath
  if ($ExpectedInstallerSha -and $actualSha -ne $ExpectedInstallerSha.ToLowerInvariant()) {
    throw "TOOLCHAIN_INSTALL_FAILED: MT5 installer SHA-256 mismatch"
  }
  $proc = Start-Process -FilePath $installerPath -ArgumentList "/auto" -PassThru -Wait
  if ($proc.ExitCode -ne 0) { throw "TOOLCHAIN_INSTALL_FAILED: MT5 installer exited $($proc.ExitCode)" }

  $candidates = @(
    (Join-Path $env:ProgramFiles "MetaTrader 5/MetaEditor64.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs/MetaTrader 5/MetaEditor64.exe")
  )
  $deadline = [DateTime]::UtcNow.AddSeconds(120)
  while ([DateTime]::UtcNow -lt $deadline) {
    foreach ($candidate in $candidates) {
      if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        return [ordered]@{ path=(Resolve-Path $candidate).Path; installer_sha256=$actualSha; installed=$true }
      }
    }
    $found = Get-ChildItem -Path $env:ProgramFiles,$env:LOCALAPPDATA -Filter MetaEditor64.exe -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
      return [ordered]@{ path=$found.FullName; installer_sha256=$actualSha; installed=$true }
    }
    Start-Sleep -Seconds 2
  }
  throw "TOOLCHAIN_INSTALL_FAILED: MetaEditor64.exe not found after MT5 installation"
}

function Copy-NormalizedTree([string]$Source, [string]$Destination) {
  if (-not (Test-Path -LiteralPath $Source -PathType Container)) { return }
  $srcRoot = (Resolve-Path -LiteralPath $Source).Path
  New-Item -ItemType Directory -Force -Path $Destination | Out-Null
  foreach ($item in Get-ChildItem -LiteralPath $srcRoot -File -Recurse) {
    $rel = [System.IO.Path]::GetRelativePath($srcRoot, $item.FullName)
    $parts = $rel -split '[\\/]'
    if ($parts -contains ".git" -or $parts -contains ".venv" -or $parts -contains "__pycache__" -or $parts -contains "evidence") { continue }
    $dest = Join-Path $Destination $rel
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
    if ($item.Extension.ToLowerInvariant() -in @(".mq5", ".mqh")) {
      $text = Read-TextAnyEncoding $item.FullName
      [System.IO.File]::WriteAllText($dest, $text, (New-Object System.Text.UnicodeEncoding($false, $true)))
    } else {
      Copy-Item -LiteralPath $item.FullName -Destination $dest -Force
    }
  }
}

function Relative-Under([string]$Root, [string]$Path) {
  $rootAbs = (Resolve-Path -LiteralPath $Root).Path
  $pathAbs = (Resolve-Path -LiteralPath $Path).Path
  $rel = [System.IO.Path]::GetRelativePath($rootAbs, $pathAbs).Replace("\", "/")
  if ($rel -eq ".." -or $rel.StartsWith("../")) { throw "SOURCE_STAGE_FAILED: target escapes project root" }
  return $rel
}

function Map-StagedTarget([string]$Relative, [string]$Mql5Root, [bool]$HasMql5Tree, [bool]$HasKnownTree) {
  $rel = $Relative.Replace("\", "/")
  if ($HasMql5Tree -and $rel.StartsWith("MQL5/", [StringComparison]::OrdinalIgnoreCase)) {
    return Join-Path $Mql5Root $rel.Substring(5)
  }
  $first = ($rel -split '/')[0]
  if ($HasKnownTree -and $first -in @("Experts","Include","Indicators","Libraries","Scripts")) {
    return Join-Path $Mql5Root $rel
  }
  return Join-Path (Join-Path $Mql5Root "Experts/__vkmql_project") $rel
}

function Get-TargetPlan([string]$PrimaryTarget, [string]$Json) {
  $items = @()
  if ($Json) {
    $parsed = $Json | ConvertFrom-Json
    foreach ($raw in @($parsed)) {
      if ($raw -is [string]) {
        $items += [ordered]@{ id=[System.IO.Path]::GetFileNameWithoutExtension([string]$raw); source=[string]$raw; required=$true }
      } else {
        $source = [string]$raw.source
        $id = if ($raw.id) { [string]$raw.id } else { [System.IO.Path]::GetFileNameWithoutExtension($source) }
        $required = if ($raw.PSObject.Properties.Name -contains 'required') { [bool]$raw.required } else { $true }
        $items += [ordered]@{ id=$id; source=$source; required=$required }
      }
    }
  } else {
    $items += [ordered]@{ id=[System.IO.Path]::GetFileNameWithoutExtension($PrimaryTarget); source=$PrimaryTarget; required=$true }
  }
  if ($items.Count -eq 0) { throw "SOURCE_STAGE_FAILED: compile target plan is empty" }
  $seen = @{}
  foreach ($item in $items) {
    if (-not $item.id -or $item.id -notmatch '^[A-Za-z0-9_.-]+$') { throw "SOURCE_STAGE_FAILED: unsafe target id '$($item.id)'" }
    if ($seen.ContainsKey($item.id)) { throw "SOURCE_STAGE_FAILED: duplicate target id '$($item.id)'" }
    $seen[$item.id] = $true
  }
  return @($items)
}

function Parse-CompileLog([string]$LogPath, [string]$Ex5Path) {
  $codes = New-Object System.Collections.Generic.List[string]
  $errors = 0
  $warnings = 0
  $summary = ""
  $text = ""
  if (-not (Test-Path -LiteralPath $LogPath -PathType Leaf)) {
    $codes.Add("LOG_MISSING")
  } else {
    $text = Read-TextAnyEncoding $LogPath
    $match = [regex]::Match($text, 'Result:\s*(\d+)\s+errors?\s*,\s*(\d+)\s+warnings?', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    if (-not $match.Success) {
      $codes.Add("RESULT_MISSING")
    } else {
      $summary = $match.Value
      $errors = [int]$match.Groups[1].Value
      $warnings = [int]$match.Groups[2].Value
      if ($errors -ne 0) { $codes.Add("COMPILE_ERRORS") }
      if ($warnings -ne 0) { $codes.Add("COMPILE_WARNINGS") }
    }
  }
  if (-not (Test-Path -LiteralPath $Ex5Path -PathType Leaf)) { $codes.Add("EX5_MISSING") }
  return [ordered]@{
    ok=($codes.Count -eq 0); error_count=$errors; warning_count=$warnings; result_summary=$summary;
    failure_codes=@($codes); raw_log=$text
  }
}

function Invoke-CompileOne([string]$Id, [string]$StagedTarget, [string]$OutDir, [string]$MetaEditorPath, [int]$TimeoutSec) {
  New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
  $tempLog = Join-Path $OutDir "metaeditor.raw.log"
  $logOut = Join-Path $OutDir "compile-log.txt"
  $ex5Source = [System.IO.Path]::ChangeExtension($StagedTarget, ".ex5")
  $ex5Out = Join-Path $OutDir "ea.ex5"
  Remove-Item -LiteralPath $tempLog,$logOut,$ex5Source,$ex5Out -Force -ErrorAction SilentlyContinue

  $started = [DateTime]::UtcNow
  $arguments = @("/compile:`"$StagedTarget`"", "/log:`"$tempLog`"")
  $process = Start-Process -FilePath $MetaEditorPath -ArgumentList $arguments -PassThru
  if (-not $process.WaitForExit($TimeoutSec * 1000)) {
    try { $process.Kill($true) } catch {}
    return [ordered]@{ id=$Id; ok=$false; error_count=0; warning_count=0; result_summary=""; failure_codes=@("TIMEOUT"); returncode=$null; log_path=$logOut; ex5_path=$ex5Out }
  }
  $returnCode = $process.ExitCode
  $parsed = Parse-CompileLog $tempLog $ex5Source
  if (Test-Path -LiteralPath $tempLog -PathType Leaf) { Copy-Item -LiteralPath $tempLog -Destination $logOut -Force }
  if (Test-Path -LiteralPath $ex5Source -PathType Leaf) { Copy-Item -LiteralPath $ex5Source -Destination $ex5Out -Force }
  return [ordered]@{
    id=$Id; ok=[bool]$parsed.ok; error_count=[int]$parsed.error_count; warning_count=[int]$parsed.warning_count;
    result_summary=[string]$parsed.result_summary; failure_codes=@($parsed.failure_codes); returncode=$returnCode;
    log_path=$logOut; ex5_path=$ex5Out; duration_ms=[int](([DateTime]::UtcNow - $started).TotalMilliseconds)
  }
}

function Get-GitHubJobId([string]$Token) {
  if (-not $Token -or -not $env:GITHUB_REPOSITORY -or -not $env:GITHUB_RUN_ID) { return "" }
  try {
    $api = if ($env:GITHUB_API_URL) { $env:GITHUB_API_URL.TrimEnd('/') } else { "https://api.github.com" }
    $headers = @{ Authorization="Bearer $Token"; Accept="application/vnd.github+json"; "X-GitHub-Api-Version"="2022-11-28" }
    $data = Invoke-RestMethod -Headers $headers -Uri "$api/repos/$($env:GITHUB_REPOSITORY)/actions/runs/$($env:GITHUB_RUN_ID)/jobs?per_page=100" -Method Get
    $match = @($data.jobs | Where-Object { $_.name -eq $env:GITHUB_JOB -or $_.status -eq "in_progress" } | Select-Object -First 1)
    if ($match.Count -gt 0) { return [string]$match[0].id }
  } catch {
    Write-Warning "Unable to resolve GitHub numeric job id: $($_.Exception.Message)"
  }
  return ""
}

$root = (Resolve-Path -LiteralPath $ProjectRoot).Path
$out = if ([System.IO.Path]::IsPathRooted($EvidenceDir)) { $EvidenceDir } else { Join-Path $root $EvidenceDir }
New-Item -ItemType Directory -Force -Path $out | Out-Null
$resultPath = Join-Path $out "result.json"
$topFailureCodes = New-Object System.Collections.Generic.List[string]
$targetResults = @()
$toolchain = [ordered]@{ probe_ok=$false; stdlib_warmed=$false }
$metaInfo = [ordered]@{ path=""; version=""; installer_sha256="" }
$sourceCommit = ""
$sourceTree = ""
$jobId = ""

try {
  $sourceCommit = (& git -C $root rev-parse HEAD).Trim()
  $sourceTree = (& git -C $root rev-parse 'HEAD^{tree}').Trim()
  if ($LASTEXITCODE -ne 0 -or $sourceCommit -notmatch '^[0-9a-fA-F]{40}$' -or $sourceTree -notmatch '^[0-9a-fA-F]{40}$') {
    throw "SOURCE_BINDING_MISMATCH: project root is not bound to a full git commit/tree"
  }
  $sourceCommit = $sourceCommit.ToLowerInvariant()
  $sourceTree = $sourceTree.ToLowerInvariant()
  if ($ExpectedCommit -and $sourceCommit -ne $ExpectedCommit.ToLowerInvariant()) {
    throw "SOURCE_BINDING_MISMATCH: checked-out commit does not match expected commit"
  }

  $plans = Get-TargetPlan $Target $TargetsJson
  foreach ($plan in $plans) {
    $candidate = if ([System.IO.Path]::IsPathRooted([string]$plan.source)) { [string]$plan.source } else { Join-Path $root ([string]$plan.source) }
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "SOURCE_STAGE_FAILED: target not found: $($plan.source)" }
    $plan['relative'] = Relative-Under $root $candidate
    $plan['original_path'] = (Resolve-Path -LiteralPath $candidate).Path
    $plan['original_sha256'] = Sha256 $candidate
    $plan['original_encoding'] = Detect-Encoding $candidate
  }

  $resolvedMeta = Resolve-MetaEditor $MetaEditor $InstallerUrl $InstallerSha256
  $metaPath = [string]$resolvedMeta.path
  $metaInfo.path = $metaPath
  $metaInfo.installer_sha256 = [string]$resolvedMeta.installer_sha256
  $metaInfo.version = [string](Get-Item -LiteralPath $metaPath).VersionInfo.FileVersion
  $installRoot = Split-Path -Parent $metaPath
  $mql5Root = Join-Path $installRoot "MQL5"
  New-Item -ItemType Directory -Force -Path $mql5Root | Out-Null

  $hasMql5Tree = Test-Path -LiteralPath (Join-Path $root "MQL5") -PathType Container
  $knownDirs = @("Experts","Include","Indicators","Libraries","Scripts")
  $hasKnownTree = [bool]($knownDirs | Where-Object { Test-Path -LiteralPath (Join-Path $root $_) -PathType Container } | Select-Object -First 1)
  if ($hasMql5Tree) {
    Copy-NormalizedTree (Join-Path $root "MQL5") $mql5Root
  } elseif ($hasKnownTree) {
    foreach ($dir in $knownDirs) { Copy-NormalizedTree (Join-Path $root $dir) (Join-Path $mql5Root $dir) }
  } else {
    Copy-NormalizedTree $root (Join-Path $mql5Root "Experts/__vkmql_project")
  }

  $needsAngleInclude = $false
  foreach ($plan in $plans) {
    if ((Read-TextAnyEncoding ([string]$plan.original_path)) -match '(?m)^\s*#include\s*<') { $needsAngleInclude = $true; break }
  }
  $tradeHeader = Join-Path $mql5Root "Include/Trade/Trade.mqh"
  $shouldWarm = $WarmStdlib -eq "always" -or ($WarmStdlib -eq "auto" -and $needsAngleInclude -and -not (Test-Path -LiteralPath $tradeHeader))
  if ($shouldWarm) {
    $terminal = Join-Path $installRoot "terminal64.exe"
    if (Test-Path -LiteralPath $terminal -PathType Leaf) {
      $terminalProc = Start-Process -FilePath $terminal -ArgumentList "/portable" -PassThru
      Start-Sleep -Seconds 20
      try { if (-not $terminalProc.HasExited) { $terminalProc.Kill($true) } } catch {}
      $toolchain.stdlib_warmed = $true
    }
  }

  $probeDir = Join-Path $mql5Root "Experts/__vkmql_probe"
  New-Item -ItemType Directory -Force -Path $probeDir | Out-Null
  $probeSource = Join-Path $probeDir "ProbeEA.mq5"
  $probeText = "#property strict`r`nint OnInit(){ return(INIT_SUCCEEDED); }`r`nvoid OnTick(){}`r`n"
  [System.IO.File]::WriteAllText($probeSource, $probeText, (New-Object System.Text.UnicodeEncoding($false, $true)))
  $probe = Invoke-CompileOne "toolchain-probe" $probeSource (Join-Path $out "toolchain") $metaPath $TimeoutSeconds
  if (-not $probe.ok) { throw "TOOLCHAIN_PROBE_FAILED: MetaEditor ProbeEA did not compile 0 errors / 0 warnings with EX5" }
  $toolchain.probe_ok = $true

  foreach ($plan in $plans) {
    $staged = Map-StagedTarget ([string]$plan.relative) $mql5Root $hasMql5Tree $hasKnownTree
    if (-not (Test-Path -LiteralPath $staged -PathType Leaf)) { throw "SOURCE_STAGE_FAILED: staged target missing: $staged" }
    $targetOut = Join-Path (Join-Path $out "targets") ([string]$plan.id)
    $compiled = Invoke-CompileOne ([string]$plan.id) $staged $targetOut $metaPath $TimeoutSeconds
    $compiled.source = [string]$plan.relative
    $compiled.required = [bool]$plan.required
    $compiled.original_sha256 = [string]$plan.original_sha256
    $compiled.staged_sha256 = Sha256 $staged
    $compiled.original_encoding = [string]$plan.original_encoding
    $compiled.compiler_encoding = "utf-16-le-bom"
    $targetResults += $compiled
    if ($plan.required -and -not $compiled.ok) {
      foreach ($code in @($compiled.failure_codes)) { if (-not $topFailureCodes.Contains([string]$code)) { $topFailureCodes.Add([string]$code) } }
    }
  }

  $jobId = Get-GitHubJobId $GitHubToken
  if (-not $jobId -or $jobId -notmatch '^\d+$') { $topFailureCodes.Add("SOURCE_BINDING_MISMATCH") }
} catch {
  $message = [string]$_.Exception.Message
  $known = @("TOOLCHAIN_INSTALL_FAILED","TOOLCHAIN_PROBE_FAILED","SOURCE_STAGE_FAILED","SOURCE_BINDING_MISMATCH") | Where-Object { $message.StartsWith($_) } | Select-Object -First 1
  $code = if ($known) { [string]$known } else { "INVOCATION_FAILED" }
  if (-not $topFailureCodes.Contains($code)) { $topFailureCodes.Add($code) }
  Write-Error $message -ErrorAction Continue
}

$requiredFailed = @($targetResults | Where-Object { $_.required -and -not $_.ok }).Count -gt 0
$overallOk = ($topFailureCodes.Count -eq 0 -and -not $requiredFailed -and $targetResults.Count -gt 0 -and $toolchain.probe_ok)
$primary = if ($targetResults.Count -gt 0) { $targetResults[0] } else { $null }
$artifacts = @()
if ($primary) {
  if (Test-Path -LiteralPath $primary.log_path -PathType Leaf) {
    $canonicalLog = Join-Path $out "compile-log.txt"
    Copy-Item -LiteralPath $primary.log_path -Destination $canonicalLog -Force
    $artifacts += [ordered]@{ role="compile_log"; filename="compile-log.txt"; sha256=(Sha256 $canonicalLog); size_bytes=(Get-Item $canonicalLog).Length; required=$true }
  }
  if (Test-Path -LiteralPath $primary.ex5_path -PathType Leaf) {
    $canonicalEx5 = Join-Path $out "ea.ex5"
    Copy-Item -LiteralPath $primary.ex5_path -Destination $canonicalEx5 -Force
    $artifacts += [ordered]@{ role="compiled_ex5"; filename="ea.ex5"; sha256=(Sha256 $canonicalEx5); size_bytes=(Get-Item $canonicalEx5).Length; required=$true }
  }
}
foreach ($item in $targetResults | Select-Object -Skip 1) {
  if (Test-Path -LiteralPath $item.log_path -PathType Leaf) {
    $rel = "targets/$($item.id)/compile-log.txt"
    $artifacts += [ordered]@{ role="compile_log:$($item.id)"; filename=$rel; sha256=(Sha256 $item.log_path); size_bytes=(Get-Item $item.log_path).Length; required=[bool]$item.required }
  }
  if (Test-Path -LiteralPath $item.ex5_path -PathType Leaf) {
    $rel = "targets/$($item.id)/ea.ex5"
    $artifacts += [ordered]@{ role="compiled_ex5:$($item.id)"; filename=$rel; sha256=(Sha256 $item.ex5_path); size_bytes=(Get-Item $item.ex5_path).Length; required=[bool]$item.required }
  }
}

$now = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
$status = if ($overallOk) { "PASS" } else { "FAIL" }
$primaryErrors = if ($primary) { [int]$primary.error_count } else { 0 }
$primaryWarnings = if ($primary) { [int]$primary.warning_count } else { 0 }
$primaryTarget = if ($primary) { [string]$primary.source } else { $Target }
$primaryTargetSha = if ($primary) { [string]$primary.original_sha256 } else { "" }
$primaryStagedSha = if ($primary) { [string]$primary.staged_sha256 } else { "" }
$primaryEncoding = if ($primary) { [string]$primary.original_encoding } else { "" }
$canonicalLogPath = Join-Path $out "compile-log.txt"
$canonicalEx5Path = Join-Path $out "ea.ex5"
$logSha = if (Test-Path -LiteralPath $canonicalLogPath -PathType Leaf) { Sha256 $canonicalLogPath } else { "" }
$ex5Sha = if (Test-Path -LiteralPath $canonicalEx5Path -PathType Leaf) { Sha256 $canonicalEx5Path } else { "" }
$provReturnCode = if ($overallOk) { 0 } else { 1 }
$result = [ordered]@{
  schema_version="1.0"; source="github_actions_metaeditor"; ok=$overallOk; status=$status;
  error_count=$primaryErrors; warning_count=$primaryWarnings; failure_codes=@($topFailureCodes); target=$primaryTarget;
  target_sha256=$primaryTargetSha; staged_sha256=$primaryStagedSha; log_sha256=$logSha; ex5_sha256=$ex5Sha;
  source_commit=$sourceCommit; source_tree_sha=$sourceTree; tool_version=$KitVersion;
  encoding=[ordered]@{ original=$primaryEncoding; compiler="utf-16-le-bom"; transformation="encoding_only" };
  runner=[ordered]@{ os=$env:RUNNER_OS; arch=$env:RUNNER_ARCH; name=$env:RUNNER_NAME };
  github=[ordered]@{ repository=$env:GITHUB_REPOSITORY; run_id=$env:GITHUB_RUN_ID; run_attempt=$env:GITHUB_RUN_ATTEMPT; job=$env:GITHUB_JOB; job_id=$jobId; workflow_ref=$env:GITHUB_WORKFLOW_REF; action_ref=$env:GITHUB_ACTION_REF };
  metaeditor=$metaInfo; toolchain=$toolchain; targets=$targetResults; artifacts=$artifacts;
  provenance=[ordered]@{ source="github_actions_metaeditor"; command="MetaEditor64.exe /compile:<staged-target> /log:<compile-log>"; tool_version=$KitVersion; host=[Environment]::MachineName; recorded_at_utc=$now; returncode=$provReturnCode }
}
Write-Utf8Json $result $resultPath 20

if ($env:GITHUB_STEP_SUMMARY) {
  Add-Content -LiteralPath $env:GITHUB_STEP_SUMMARY -Value "## VibeCodeKit MQL5 native compile"
  Add-Content -LiteralPath $env:GITHUB_STEP_SUMMARY -Value "- Status: **$($result.status)**"
  Add-Content -LiteralPath $env:GITHUB_STEP_SUMMARY -Value "- Target: ``$($result.target)``"
  Add-Content -LiteralPath $env:GITHUB_STEP_SUMMARY -Value "- Errors / warnings: $($result.error_count) / $($result.warning_count)"
  Add-Content -LiteralPath $env:GITHUB_STEP_SUMMARY -Value "- Source commit: ``$sourceCommit``"
}

if (-not $overallOk) {
  throw "VibeCodeKit native compile failed: $(@($topFailureCodes) -join ',')"
}
Write-Host "VibeCodeKit native compile PASS: 0 errors, 0 warnings, EX5 present"
