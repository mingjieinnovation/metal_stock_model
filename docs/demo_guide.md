# Demo Guide: Metal Stock Model

This guide is written for a portfolio, interview or stakeholder walkthrough. The recommended demo length is 3-5 minutes.

## One-sentence pitch

Metal Stock Model is an audit-first research pipeline for Chinese metals equities: it connects market data, commodity prices, filings, production data and quality gates, then explains whether each output is usable as valuation, observation or alert.

## Suggested demo flow

### 1. Open the landing page

Use the GitHub Pages link:

```text
https://mingjieinnovation.github.io/metal_stock_model/
```

Explain that the page is a public-facing portfolio layer. It intentionally excludes raw market data, credentials and private runtime artifacts.

### 2. Show the pipeline structure

Point to the four stages:

1. Acquire
2. Audit
3. Evaluate
4. Guardrail

The important message is that the project is not only about prediction. It is about making model reliability visible.

### 3. Open the latest decision table

Report:

```text
reports/v2_latest_decision_table.md
```

What to say:

- Each company has a latest model status.
- The system separates valuation anchor, observation and alert.
- `can_trade=False` is not a bug; it means the quality gate is doing its job.

### 4. Open the data-quality gate

Report:

```text
reports/v2_data_quality_gate.md
```

What to say:

- This report explains why a signal is downgraded.
- Missing strict data is not silently filled.
- Proxy-heavy factors are disclosed instead of hidden.

### 5. Open the factor lineage report

Report:

```text
reports/v2_factor_data_lineage.md
```

What to say:

- Each factor has a definition, source and quality label.
- This is useful for model governance and future upgrades.
- The project treats data provenance as part of the model, not an afterthought.

### 6. Open the daily alert

Report:

```text
reports/v2_daily_alert.md
```

What to say:

- Daily output is only a short-term gap alert.
- It cannot independently create a tradable signal.
- This prevents noisy daily moves from overriding slower fundamental valuation.

## Strong talking points

- The model has explicit use-case separation: monthly valuation, weekly observation, daily alert.
- It uses quality gates to avoid overstating weak signals.
- It keeps an audit trail of API failures, cache usage and proxy data.
- It is designed to be maintainable: new real data sources can replace proxies without changing the whole workflow.

## What not to claim

Do not present this as:

- financial advice
- a production trading strategy
- a guaranteed alpha model
- a fully strict fundamental model for every factor

Better phrasing:

> This is a research automation and model-governance demo. Its value is not just the forecast, but the way it makes data quality and model boundaries visible.

## If someone asks what you would improve next

Answer:

1. Replace proxy cost factors with real power, anode and coal price APIs.
2. Add stricter Chalco production volume parsing from filings.
3. Reduce Zijin demand-score proxy reliance with real inventory, ETF and FX/risk data.
4. Add dashboard charts for valuation range, actual price and quality status over time.
