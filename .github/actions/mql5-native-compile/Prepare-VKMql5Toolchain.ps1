param(
  [string]$MetaEditor = "",
  [string]$InstallerUrl = "",
  [string]$InstallerSha256 = "",
  [string]$ProjectRoot = ".",
  [Parameter(Mandatory=$true)][string]$Target,
  [string]$TargetsJson = "",
  [ValidateSet("auto","always","never")][string]$WarmStdlib = "auto"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Sha256([string]$Path) {
  return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Assert-SafeHttpsUrl([string]$Url) {
  $uri = [Uri]$Url
  if ($uri.Scheme -ne "https") { throw "TOOLCHAIN_INSTALL_FAILED: installer URL must use https" }
  $hostName = $uri.DnsSafeHost.ToLowerInvariant()
  if ($hostName -in @("localhost","0.0.0.0","::1") -or $hostName.StartsWith("127.") -or $hostName.StartsWith("169.254.")) {
    throw "TOOLCHAIN_INSTALL_FAILED: installer URL resolves to a forbidden local/link-local host name"
  }
}

function Set-ActionOutput([string]$Name, [string]$Value) {
  if ($env:GITHUB_OUTPUT) {
    Add-Content -LiteralPath $env:GITHUB_OUTPUT -Value "$Name=$Value"
  }
  Write-Host "$Name=$Value"
}

function Find-MetaEditor {
  $candidates = @(
    (Join-Path $env:ProgramFiles "MetaTrader 5/MetaEditor64.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs/MetaTrader 5/MetaEditor64.exe")
  )
  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }
  $found = Get-ChildItem -Path $env:ProgramFiles,$env:LOCALAPPDATA -Filter MetaEditor64.exe -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($found) { return $found.FullName }
  return ""
}

function Resolve-MetaEditorPath {
  if ($MetaEditor) {
    $resolved = Resolve-Path -LiteralPath $MetaEditor -ErrorAction SilentlyContinue
    if (-not $resolved) { throw "TOOLCHAIN_INSTALL_FAILED: MetaEditor override not found: $MetaEditor" }
    return [ordered]@{ path=$resolved.Path; installer_sha256=""; installer_exit_code=$null }
  }

  if (-not $InstallerUrl) { throw "TOOLCHAIN_INSTALL_FAILED: MetaEditor path or installer-url is required" }
  Assert-SafeHttpsUrl $InstallerUrl
  $installerPath = Join-Path $env:RUNNER_TEMP "vkmql-mt5setup.exe"
  Invoke-WebRequest -Uri $InstallerUrl -OutFile $installerPath -UseBasicParsing
  $actualSha = Sha256 $installerPath
  if ($InstallerSha256 -and $actualSha -ne $InstallerSha256.ToLowerInvariant()) {
    throw "TOOLCHAIN_INSTALL_FAILED: MT5 installer SHA-256 mismatch"
  }

  $proc = Start-Process -FilePath $installerPath -ArgumentList "/auto" -PassThru -Wait
  $exitCode = $proc.ExitCode
  Start-Sleep -Seconds 10
  Get-Process -Name terminal64 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

  $deadline = [DateTime]::UtcNow.AddSeconds(120)
  do {
    $resolvedPath = Find-MetaEditor
    if ($resolvedPath) {
      if ($exitCode -ne 0) {
        Write-Warning "MT5 installer exited $exitCode, but MetaEditor64.exe is present; accepting observed installation state."
      }
      return [ordered]@{ path=$resolvedPath; installer_sha256=$actualSha; installer_exit_code=$exitCode }
    }
    Start-Sleep -Seconds 2
  } while ([DateTime]::UtcNow -lt $deadline)

  throw "TOOLCHAIN_INSTALL_FAILED: MetaEditor64.exe not found after MT5 installer exit $exitCode"
}

function Get-TargetSources([string]$Root, [string]$Primary, [string]$Json) {
  $sources = New-Object System.Collections.Generic.List[string]
  if ($Json) {
    $parsed = $Json | ConvertFrom-Json
    foreach ($raw in @($parsed)) {
      if ($raw -is [string]) { $sources.Add([string]$raw) }
      elseif ($raw.PSObject.Properties.Name -contains 'source') { $sources.Add([string]$raw.source) }
    }
  } else {
    $sources.Add($Primary)
  }
  $resolved = @()
  foreach ($source in $sources) {
    $candidate = if ([System.IO.Path]::IsPathRooted($source)) { $source } else { Join-Path $Root $source }
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { $resolved += (Resolve-Path -LiteralPath $candidate).Path }
  }
  return @($resolved)
}

function Needs-StdlibWarm([string]$Root, [string]$Primary, [string]$Json) {
  if ($WarmStdlib -eq "never") { return $false }
  if ($WarmStdlib -eq "always") { return $true }
  foreach ($source in Get-TargetSources $Root $Primary $Json) {
    $text = [System.IO.File]::ReadAllText($source)
    if ($text -match '(?m)^\s*#include\s*<') { return $true }
  }
  return $false
}

function Find-TradeHeader([string]$InstallRoot) {
  $direct = Join-Path $InstallRoot "MQL5/Include/Trade/Trade.mqh"
  if (Test-Path -LiteralPath $direct -PathType Leaf) { return (Resolve-Path -LiteralPath $direct).Path }
  $terminalData = Join-Path $env:APPDATA "MetaQuotes/Terminal"
  if (Test-Path -LiteralPath $terminalData -PathType Container) {
    $found = Get-ChildItem -LiteralPath $terminalData -Filter Trade.mqh -File -Recurse -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match '[\\/]MQL5[\\/]Include[\\/]Trade[\\/]Trade\.mqh$' } |
      Select-Object -First 1
    if ($found) { return $found.FullName }
  }
  return ""
}

function Ensure-Stdlib([string]$MetaEditorPath, [bool]$Required) {
  if (-not $Required) { return $false }
  $installRoot = Split-Path -Parent $MetaEditorPath
  $existing = Find-TradeHeader $installRoot
  if ($existing) {
    Write-Host "MQL5 stdlib already present: $existing"
    return $true
  }

  $terminal = Join-Path $installRoot "terminal64.exe"
  if (-not (Test-Path -LiteralPath $terminal -PathType Leaf)) {
    throw "TOOLCHAIN_STDLIB_FAILED: terminal64.exe missing; cannot materialize MQL5 standard library"
  }

  $terminalProc = Start-Process -FilePath $terminal -PassThru
  Start-Sleep -Seconds 45
  try { if (-not $terminalProc.HasExited) { $terminalProc.Kill($true) } } catch {}
  Start-Sleep -Seconds 5

  $header = Find-TradeHeader $installRoot
  if (-not $header) {
    throw "TOOLCHAIN_STDLIB_FAILED: Trade/Trade.mqh not materialized after 45-second terminal warmup"
  }
  Write-Host "MQL5 stdlib verified: $header"
  return $true
}

$root = (Resolve-Path -LiteralPath $ProjectRoot).Path
$resolved = Resolve-MetaEditorPath
$metaPath = [string]$resolved.path
$warmRequired = Needs-StdlibWarm $root $Target $TargetsJson
$stdlibReady = Ensure-Stdlib $metaPath $warmRequired

Set-ActionOutput "metaeditor" $metaPath
Set-ActionOutput "installer_sha256" ([string]$resolved.installer_sha256)
Set-ActionOutput "stdlib_warmed" ($(if ($stdlibReady) { "true" } else { "false" }))
