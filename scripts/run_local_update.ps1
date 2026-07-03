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

Import-DotEnv (Join-Path $ProjectRoot ".env")
Import-DotEnv (Join-Path $ProjectRoot ".env.local")

if (!$env:FEISHU_KEYWORD) { $env:FEISHU_KEYWORD = "metal_stock_model" }
if (!$FullProxyRefresh) { $env:V2_SKIP_PUBLIC_PROXY_REFRESH = "1" }
$env:V2_RUN_TYPE = "local_$Type"

Write-Host "== metal_stock_model local update: $Type =="
Write-Host "ProjectRoot=$ProjectRoot"
Write-Host "FEISHU_WEBHOOK_SET=$([bool]$env:FEISHU_WEBHOOK)"
Write-Host "FullProxyRefresh=$([bool]$FullProxyRefresh)"

switch ($Type) {
    "daily" {
        python -m src.update_daily_market
        python -m src.v2_data_quality_gate
        python -m src.v2_latest_decision_table
        python -m src.v2_model_update_log
        python -m src.notify_feishu --type daily
    }
    "weekly" {
        python -m src.update_daily_market
        python -m src.update_weekly_signal
        python -m src.v2_data_quality_gate
        python -m src.v2_latest_decision_table
        python -m src.v2_model_update_log
        python -m src.notify_feishu --type weekly
    }
    "monthly" {
        python -m src.update_daily_market
        python -m src.update_monthly_valuation
        python -m src.v2_data_quality_gate
        python -m src.v2_latest_decision_table
        python -m src.v2_model_update_log
        python -m src.notify_feishu --type monthly
    }
    "quarterly" {
        python -m src.update_quarterly_fundamentals
        python -m src.v2_data_gap_dashboard
        python -m src.v2_data_quality_gate
        python -m src.v2_latest_decision_table
        python -m src.v2_model_update_log
        python -m src.notify_feishu --type quarterly
    }
}

Write-Host "== done =="
