# V2 模型使用指南

## 紫金矿业
- 月度用于估值中枢，周度用于交易观察，日度只做 gap alert。
- 只有 strict production 可见、需求分数未被默认代理主导、gap<-12% 且铜金趋势确认时，才讨论低估观察；不是自动买卖。

## 中国铝业
- 当前不能用单点 gap 交易。优先使用 V2.3-K Bear/Base/Bull：低于 Bear 才是极端低估观察；Bear-Base 需基本面确认；Base-Bull 为合理区间；高于 Bull 表示高景气预期已较充分反映。
- 只有 OOS季度≥10、OOS R²>0、MAPE≤15%、|Bias|≤3亿元且周月同向，才可 candidate_signal；当前不满足。
