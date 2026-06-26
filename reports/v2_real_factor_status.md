# V2 外部真实因子状态

本表不将缺失付费数据伪装成代理。FRED、WGC 和公开库存等数据均保留来源状态。

| source_type | data_quality_flag | 记录数 |
|---|---|---|
| BLOCKED | BLOCKED_NEEDS_PAID_DATA | 6 |
| BLOCKED | MISSING_FRED_API_KEY | 4 |
| BLOCKED | MISSING_WGC_DATA;MISSING_WGC_COOKIE | 1 |
