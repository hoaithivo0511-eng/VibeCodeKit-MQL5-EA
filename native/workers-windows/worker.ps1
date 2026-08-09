<# 
Minimal Windows worker reference implementation.

This file documents the expected worker behavior. For production, run it behind
a proper service wrapper with authentication, job isolation, cleanup, and TLS.

Protocol endpoints expected by the Python client:
  POST /jobs
  GET  /jobs/{job_id}
  GET  /jobs/{job_id}/artifacts/{filename}

The included `run_compile.ps1` and `run_backtest.ps1` are the execution payloads
that a worker service should call per job.
#>

param(
  [string]$ConfigPath = ".\worker_config.json"
)

Write-Host "VibeCodeKit Windows worker reference"
Write-Host "Load config: $ConfigPath"
Write-Host "Use run_compile.ps1 and run_backtest.ps1 inside your HTTP service implementation."
Write-Host "This reference script intentionally does not expose an unauthenticated HTTP server."


# Worker service implementer note:
# Each POST /jobs payload may contain payload.bundle.zip_base64.
# Decode it into the per-job workspace before invoking run_compile.ps1 or run_backtest.ps1.
# Verify payload.bundle.sha256 before execution.
