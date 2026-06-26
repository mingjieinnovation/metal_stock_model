# V2 最新决策表

此表为研究用途；中国铝业不输出交易信号，质量闸门不通过时所有结果自动降级。

| company | main_model | actual_price | model_price_or_range | bear_price | base_price | bull_price | gap | price_zone | data_quality_score | proxy_ratio | signal_status | can_trade | reason | next_watch_item |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 中国铝业 | V2.3-K Bear/Base/Bull | 11.42 | 8.03 / 9.45 / 11.56 | 8.030361957741361 | 9.447484656166308 | 11.555118733397174 |  | fair_value_zone | 0.57 | 0.43 | valuation_anchor_only | False | V2.3 仅允许区间估值；Model J 仍缺严格产量，且 OOS 条件未满足。 | 严格原铝产量与氧化铝外销量 |
| 紫金矿业 | V2.1 strict 铜金收入模型 | 30.44 | 31.14328894640177 |  |  |  | -0.02258235948079035 | fair_value_zone | 0.43 | 0.57 | valuation_observation | False | 严格产量已接入；若需求分数仍由默认代理主导，则自动降级为观察。 | DFII10、美元指数、黄金 ETF 与铜库存历史 |
