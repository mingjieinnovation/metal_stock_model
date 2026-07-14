# Local update + Feishu notification

GitHub Actions scheduled updates are disabled. The intended production flow is now local-first:

```powershell
cd "C:\Users\mingj\Documents\mental prediction model\metal_stock_model"
powershell -ExecutionPolicy Bypass -File .\scripts\run_local_update.ps1 -Type daily
```

## Configure Feishu locally

Create `.env.local` from `.env.example`:

```powershell
Copy-Item .env.example .env.local
notepad .env.local
```

Fill in:

```text
FEISHU_WEBHOOK=your Feishu custom bot webhook
FEISHU_SECRET=your Feishu signing secret
FEISHU_KEYWORD=metal_stock_model
```

`.env` and `.env.local` are ignored by Git, so real secrets stay local.

## Run modes

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_local_update.ps1 -Type daily
powershell -ExecutionPolicy Bypass -File .\scripts\run_local_update.ps1 -Type weekly
powershell -ExecutionPolicy Bypass -File .\scripts\run_local_update.ps1 -Type monthly
powershell -ExecutionPolicy Bypass -File .\scripts\run_local_update.ps1 -Type quarterly
```

By default, the script sets `V2_SKIP_PUBLIC_PROXY_REFRESH=1` to avoid slow external proxy refreshes. If you want the full external refresh, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_local_update.ps1 -Type daily -FullProxyRefresh
```

## Test only Feishu

After `.env.local` is configured:

```powershell
python -m src.notify_feishu --type test
```

If `FEISHU_WEBHOOK_SET=False`, the local environment did not load the webhook.

## Prediction refresh behavior

The local runner now calls `python -m src.refresh_latest_predictions` after market data refresh. This rebuilds daily/weekly/monthly V2 market layers, refreshes Chalco V2.2/V2.3 and Zijin V2.1 latest prediction files, rewrites the daily alert, and writes `reports/v2_latest_prediction_refresh_audit.md`. It does not promote daily alerts into tradable signals.
