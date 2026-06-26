# China Aluminum V2.1 profit-model summary

- Original V2 systematically underestimates profit: True (see diagnostics).
- Original `overvalued` signal tradable: No; suspended due to profit underprediction.
- Selected V2.1 candidate by walk-forward MAPE then absolute bias: `C_profit_anchor_ridge`.
- Selection improvement versus Model A on both MAPE and absolute bias: True.
- Latest V2.1 quarterly-profit prediction: 44.41 bn RMB.
- Latest V2.1 model price at unchanged PE logic: 9.28.
- Official Chalco gap signal restored: No. The out-of-sample quarterly evaluation remains small, and demand inputs retain DEFAULT_PROXY fields. V2.1 remains a profit-layer validation result, not an investable signal.
- No PE uplift was used. All anchors are filtered through financial announcement dates; Model D weight search is confined to each historical training window.
