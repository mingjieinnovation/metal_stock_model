# Metal Stock Model

An audit-first research pipeline for Chinese metals equities, focused on:

- **Chalco / Aluminum Corporation of China** (`601600.SH`)
- **Zijin Mining** (`601899.SH`)

The project combines equity prices, commodity futures, macro proxies, financial disclosures, production data and data-quality gates into reproducible research outputs. Its core idea is simple: a model should show not only its result, but also whether the data behind that result is fresh, cached, proxied, blocked or strict enough to use.

> This repository is a research and portfolio demo. It is not investment advice and does not generate standalone tradable signals.

## Why this project matters

Commodity equities are difficult to model because their earnings are shaped by several moving parts at once: spot and futures prices, cost curves, production volumes, macro demand, inventory cycles, FX and reporting lags. A naive price model can look impressive in-sample while quietly relying on stale or unavailable data.

This project tries to make those weaknesses visible. It separates:

1. **Valuation anchor** — usually monthly, focused on fundamental value ranges.
2. **Trading observation** — usually weekly, used only when it agrees with the valuation layer.
3. **Gap alert** — daily, used only to flag short-term price deviation.

## Current model layers

### Chalco

Chalco is modeled with an aluminum value-chain framework:

- aluminum price
- alumina price
- dynamic alumina consumption coefficient candidates
- aluminum spread
- power and anode cost proxies where real data is unavailable
- quarterly profit anchors
- bear/base/bull valuation range

Important boundary: Chalco's strict segment-profit model is still blocked until reliable primary aluminum volume and external alumina sales volume are available. Until then, the output remains a valuation anchor, not a trading signal.

### Zijin Mining

Zijin is modeled with a copper-and-gold production revenue framework:

- mined copper production
- mined gold production
- copper price
- gold price
- demand and risk proxies
- strict production data parsed from public filings where available

Important boundary: Zijin has stricter production data connected, but some demand/risk factors still rely on proxy data. That keeps the output in observation mode unless the quality gate improves.

## Data governance

The data priority is:

1. API or structured public source
2. Local API cache
3. Explicit fallback file
4. Proxy value, clearly flagged
5. Blocked / missing, never silently filled

The system is designed to preserve old data if an API fails, while recording the failure. It should prefer `CACHE`, `PROXY` or `BLOCKED` labels over pretending the data is complete.

## Main reports

- [`reports/v2_latest_decision_table.md`](reports/v2_latest_decision_table.md) — latest valuation / observation status.
- [`reports/v2_daily_alert.md`](reports/v2_daily_alert.md) — daily gap alert, not a tradable signal.
- [`reports/v2_data_quality_gate.md`](reports/v2_data_quality_gate.md) — quality-gate result and downgrade reason.
- [`reports/v2_factor_data_lineage.md`](reports/v2_factor_data_lineage.md) — factor definitions, data source and reliability.
- [`reports/v2_chalco_frequency_use_case_summary.md`](reports/v2_chalco_frequency_use_case_summary.md) — monthly / weekly / daily use-case separation.
- [`reports/v2_model_update_log.md`](reports/v2_model_update_log.md) — append-only update audit trail.

## Automation

The project includes scheduled GitHub Actions for:

- daily market refresh
- weekly observation update
- monthly valuation update
- quarterly fundamental audit
- GitHub Pages demo deployment

Runtime credentials such as API keys, Feishu webhooks and paid-data tokens should be stored as GitHub Secrets, never committed to the repository.

## Local run examples

```powershell
python -m src.update_daily_market
python -m src.v2_data_quality_gate
python -m src.v2_latest_decision_table
python -m src.v2_model_update_log
```

Optional Feishu notification:

```powershell
python -m src.notify_feishu --type daily
```

## Public demo

After GitHub Pages is enabled, the demo page should be available at:

```text
https://mingjieinnovation.github.io/metal_stock_model/
```

The page is intentionally lightweight: it explains the research pipeline and links to selected Markdown reports.

## Limitations

- Public pages do not include private raw datasets, credentials or local model artifacts.
- Some high-quality cost and demand factors require paid or restricted data sources.
- Backtests are research diagnostics unless they pass strict walk-forward and quality-gate requirements.
- Daily outputs are alert-only by design.
