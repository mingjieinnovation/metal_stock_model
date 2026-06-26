# China Aluminum V2 profit-layer diagnostics

- Original profit model: `v2_chalco_original_profit_model`
- Strict output months audited: 20
- Latest date: 2026-05-31
- Latest actual price: 11.42
- Original V2 quarterly-profit prediction: 44.41 bn RMB
- Quarterly profit required to match the price at the unchanged PE: 54.67 bn RMB
- Profit shortfall: 10.26 bn RMB (18.8%)
- Latest announced quarterly-profit anchor (2026Q1): 55.27 bn RMB; its annualized same-PE price is 11.55.
- Ridge alpha mode: 0.1, appearing in 45% of audited months. This is high relative to the feature scale and is consistent with coefficient/profit-response shrinkage, but it is not the only missing economic driver.

## Conclusion

1. The low model price is primarily profit-prediction driven: 10.26 bn RMB of quarterly profit is missing at the unchanged PE; PE is not raised.
2. Original V2 systematic underprediction flag: True.
3. China Aluminum V2 strict signal is suspended because the profit model systematically underpredicts quarterly profit. The current overvaluation signal is not tradable until the profit layer is recalibrated.
4. V2.1 is required: use quarterly averages/lags, announced-profit anchors and a walk-forward comparison. No future profit or future announcement date may be used.
