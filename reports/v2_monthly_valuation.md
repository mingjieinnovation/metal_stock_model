# V2 月度估值

中铝使用 Bear/Base/Bull 区间；紫金为严格产量支撑的估值观察。

| 公司 | 日期 | 实际价格 | bear_price | base_price | bull_price | price_zone | 信号 | 说明 | model_price | gap | proxy_ratio | signal_confidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 中国铝业 | 2026-05-31 | 11.42 | 8.030361957741361 | 9.447484656166308 | 11.555118733397174 | fair_value_zone | valuation_anchor_only | 只使用 V2.3-K 区间，不使用单点 gap 交易 |  |  |  |  |
| 紫金矿业 | 2026-05-31 | 30.44 |  |  |  |  | valuation_observation | 严格产量可用；需求代理占比高时降级 | 31.14328894640177 | -0.02258235948079035 | 0.5714285714285714 | low |
