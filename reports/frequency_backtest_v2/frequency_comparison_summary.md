# V1 vs V2 frequency comparison

- V1 baseline: `v1_market_price_ridge_model` remains available in existing daily/weekly/monthly reports.
- V2 strict: failed because required production and non-default demand inputs are absent.
- V2 proxy: not emitted as an investment result because no historical production observation exists from which a permissible mean/forward-fill proxy can be formed.
- Next required data: parsed `cu_ton`, `au_kg`, inventory, and approved macro proxy sources.
