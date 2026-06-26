# V2 数据质量闸门

质量闸门未完全通过：不得输出 tradable_signal，只能输出 valuation / observation / alert。

| 检查项 | 公司 | passed | data_quality_flag | 不通过后的输出限制 |
|---|---|---|---|---|
| 股票价格不复权 | 全局 | True | 通过 | 禁止输出交易信号 |
| 商品价格最新性 | 全局 | True | MISSING_MARKET_DATA | 仅研究/报警 |
| 财报公告日可见 | 全局 | True | MISSING_ANNOUNCEMENT_INDEX | 禁止以未来财报训练 |
| 紫金严格产量 | 紫金矿业 | True | 通过 | 禁止交易信号 |
| 中铝 Model J 产量 | 中国铝业 | False | BLOCKED_MISSING_STRICT_VOLUME | 维持区间估值 |
| 紫金需求默认代理占比 | 紫金矿业 | False | PROXY_RATIO=57% | 降级为观察 |
| 中铝需求默认代理占比 | 中国铝业 | True | PROXY_RATIO=43% | 仅估值中枢 |
