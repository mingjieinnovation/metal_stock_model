param(
    [ValidateSet("daily", "weekly", "monthly", "quarterly")]
    [string]$Type = "daily",
    [switch]$FullProxyRefresh
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Import-DotEnv {
    param([string]$Path)
    if (!(Test-Path $Path)) { return }
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (!$line -or $line.StartsWith("#") -or !$line.Contains("=")) { return }
        $key, $value = $line.Split("=", 2)
        $key = $key.Trim()
        $value = $value.Trim().Trim('"').Trim("'")
        if ($key) { Set-Item -Path "Env:$key" -Value $value }
    }
}

function Run-Step {
    param([string]$Command)
    Write-Host ">> $Command"
    python -m $Command
}

Import-DotEnv (Join-Path $ProjectRoot ".env")
Import-DotEnv (Join-Path $ProjectRoot ".env.local")

if (!$env:FEISHU_KEYWORD) { $env:FEISHU_KEYWORD = "metal_stock_model" }
if (!$FullProxyRefresh) { $env:V2_SKIP_PUBLIC_PROXY_REFRESH = "1" }
$env:V2_RUN_TYPE = "local_$Type"

Write-Host "== metal_stock_model local update: $Type =="
Write-Host "ProjectRoot=$ProjectRoot"
Write-Host "FEISHU_WEBHOOK_SET=$([bool]$env:FEISHU_WEBHOOK)"
Write-Host "FullProxyRefresh=$([bool]$FullProxyRefresh)"

$failed = $false
$errorMessage = ""

try {
    switch ($Type) {
        "daily" {
            Run-Step "src.update_daily_market"
            Run-Step "src.v2_data_quality_gate"
            Run-Step "src.v2_latest_decision_table"
            Run-Step "src.v2_model_update_log"
        }
        "weekly" {
            Run-Step "src.update_daily_market"
            Run-Step "src.update_weekly_signal"
            Run-Step "src.v2_data_quality_gate"
            Run-Step "src.v2_latest_decision_table"
            Run-Step "src.v2_model_update_log"
        }
        "monthly" {
            Run-Step "src.update_daily_market"
            Run-Step "src.update_monthly_valuation"
            Run-Step "src.v2_data_quality_gate"
            Run-Step "src.v2_latest_decision_table"
            Run-Step "src.v2_model_update_log"
        }
        "quarterly" {
            Run-Step "src.update_quarterly_fundamentals"
            Run-Step "src.v2_data_gap_dashboard"
            Run-Step "src.v2_data_quality_gate"
            Run-Step "src.v2_latest_decision_table"
            Run-Step "src.v2_model_update_log"
        }
    }
}
catch {
    $failed = $true
    $errorMessage = $_.Exception.Message
    New-Item -ItemType Directory -Force reports | Out-Null
    @(
        "# Local update error",
        "",
        "- type: $Type",
        "- time: $(Get-Date -Format o)",
        "- error: $errorMessage"
    ) | Set-Content -Path reports\local_update_error.md -Encoding UTF8
    Write-Error "Local update failed before notification: $errorMessage"
}
finally {
    Write-Host ">> src.notify_feishu --type $Type"
    try {
        python -m src.notify_feishu --type $Type
    }
    catch {
        Write-Error "Feishu notification failed: $($_.Exception.Message)"
        if (!$failed) { $failed = $true }
    }
}

if ($failed) { exit 1 }
Write-Host "== done =="
