# China Aluminum V2.2 frequency use-case summary

## 1. monthly_v22_valuation_anchor

- Use: valuation center and holding judgement only. Latest V2.2 TTM model price: 9.45; gap: 20.9%; status: `research_only_v22_ttm_oos_below_target`.
- Monthly raw-signal change rate: 26.3%. Forward-return fields are 1M/3M/6M and are descriptive only.
- Conclusion: monthly is the preferred valuation anchor because its TTM profit target matches the holding/valuation horizon; it is not a stand-alone tradable signal while TTM OOS validation remains below target.

## 2. weekly_v22_trading_observation

- Use: trading observation, using 4W/13W/26W forward-return analysis. Weekly raw-signal change rate: 9.6%.
- Rule: a `stronger_signal` is eligible only when weekly and monthly raw signals are aligned. It remains `research_only_stronger_signal` until the monthly valuation anchor has sufficient OOS confirmation.
- Same-direction weekly/monthly: 11 available 4W outcomes; average return 1.73%; directional hit rate 45.5%.
- Same-direction weekly/monthly: 10 available 13W outcomes; average return 7.64%; directional hit rate 60.0%.
- Same-direction weekly/monthly: 8 available 26W outcomes; average return 16.04%; directional hit rate 50.0%.

## 3. daily_v22_gap_alert

- Use: short-term gap alert only. Daily raw-signal change rate: 5.3%, versus weekly 9.6%.
- Daily output may flag rapid price/model divergence, but it cannot independently create `tradable_signal`. Higher row count does not create more independent quarterly-profit evidence.

## Decision hierarchy

- If daily and monthly conflict: use monthly for valuation judgement, weekly for trading observation, and daily only for alerts.
- If weekly and monthly align: label the observation `research_only_stronger_signal`; do not treat it as tradable before V2.2 TTM walk-forward validation improves.
- Stability comparison: weekly is not more stable than daily by raw-signal change rate (9.6% vs 5.3%).
- No PE uplift, future financial data, future announcement dates, or volume proxy disguised as strict data are used in this framework.

## Scope boundary and stability interpretation

- The V2.2 TTM model is the monthly valuation anchor. Weekly and daily rows use announcement-safe V2.1-C raw-gap observations assigned to V2.2 operational use cases; they are not separately validated high-frequency TTM models.
- Weekly is not more stable than daily by raw-signal change rate in this sample: 9.6% versus 5.3%.
- Daily gap alerts cannot be promoted to a tradable signal: daily rows do not add independent quarterly-profit evidence, regardless of the number of observations.
