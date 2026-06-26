# China Aluminum V2.3 value-chain profit decomposition

- Model H selected k dynamically inside every expanding training window; latest selected k: 2.05. No full-sample k was used.
- H full-sample quarterly R²: 0.969; H OOS quarterly R²: 0.091; TTM R²: -1.825; OOS quarters: 6; MAPE: 28.2%; bias: -3.76 bn RMB.
- R² target reached only in diagnostic mode, not in tradable walk-forward mode.
- Model I uses explicitly labelled POWER_COST_PROXY / ANODE_COST_PROXY; Model J is blocked because strict primary-al volume and alumina external sales are unavailable.
- Scenario prices: bear 8.03; base 9.45; bull 11.56.
- Status: `research_only_or_valuation_anchor_only`. Weekly/monthly alignment is required for candidate_signal; daily is gap_alert only.
