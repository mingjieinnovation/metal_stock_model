# 真实代理 API 接入状态

## 已接入并按 `available_date <= trade_date` backward-as-of 使用

| 因子 | 接口 | 当前用途 | 覆盖/限制 |
|---|---|---|---|
| 沪铝库存 | `ak.futures_inventory_em("沪铝")` | 中铝 `inventory_score`，库存越低分数越高 | 当前约 66 条；历史不足部分仍为 `DEFAULT_PROXY` |
| 沪铜库存 | `ak.futures_inventory_em("沪铜")` | 紫金 `cu_inventory_score`，库存越低分数越高 | 当前约 66 条；历史不足部分仍为 `DEFAULT_PROXY` |
| 第二产业用电同比 | `ak.macro_china_society_electricity()` | 中铝电网/工业活动、紫金 power-grid 状态 | 月度宏观发布，以保守 30 天可见延迟接入 |
| 国房景气 | `ak.macro_china_real_estate()` | 中铝地产状态 | 月度宏观发布，以保守 30 天可见延迟接入 |
| 央行黄金储备 | `ak.macro_china_foreign_exchange_gold()` | 紫金央行购金状态，使用储备变化 | 月度数据、以保守 30 天可见延迟接入 |
| 300ETF QVIX | `ak.index_option_300etf_qvix()` | 紫金风险状态，QVIX 越高风险分数越低 | 日频市场代理，不等同海外风险或公司风险 |
| 美国10年国债收益率 | `ak.bond_zh_us_rate()` | 紫金利率状态，收益率越高分数越低 | 是名义收益率代理，**不是严格真实利率** |

## 尚未替换的默认代理

- NEV：CPCA 新能源接口当前日期解析不稳定，未写入为真实值。
- 黄金 ETF：公共 ETF 历史接口未稳定返回，未用 ETF 价格冒充 ETF 持仓/资金流。
- 美元指数：当前东方财富全局指数接口名称映射不稳定，未写入默认列。
- 中铝煤价、电价、氧化铝/原铝产量：尚无当前可审计连续序列，保持 `MISSING` 或 `DEFAULT_PROXY`，没有伪造 strict 数据。

所有实际/API 与默认代理状态都保留在 `data/processed/v2_*_market.parquet` 的 `*_score_source` 和 `data_quality_flag` 字段中。
