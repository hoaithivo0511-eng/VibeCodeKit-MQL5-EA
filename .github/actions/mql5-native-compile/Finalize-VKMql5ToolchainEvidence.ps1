param(
  [string]$ProjectRoot = ".",
  [string]$EvidenceDir = "evidence/compile",
  [string]$InstallerSha256 = "",
  [ValidateSet("true","false")][string]$StdlibWarmed = "false"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = (Resolve-Path -LiteralPath $ProjectRoot).Path
$out = if ([System.IO.Path]::IsPathRooted($EvidenceDir)) { $EvidenceDir } else { Join-Path $root $EvidenceDir }
$resultPath = Join-Path $out "result.json"
if (-not (Test-Path -LiteralPath $resultPath -PathType Leaf)) {
  Write-Host "No compile result to finalize: $resultPath"
  exit 0
}

$data = Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $data.metaeditor) { $data | Add-Member -NotePropertyName metaeditor -NotePropertyValue ([pscustomobject]@{}) }
$data.metaeditor.installer_sha256 = $InstallerSha256
if (-not $data.toolchain) { $data | Add-Member -NotePropertyName toolchain -NotePropertyValue ([pscustomobject]@{}) }
$data.toolchain.stdlib_warmed = ($StdlibWarmed -eq "true")

$json = $data | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText($resultPath, $json + "`n", (New-Object System.Text.UTF8Encoding($false)))
Write-Host "Finalized native compile toolchain evidence"
