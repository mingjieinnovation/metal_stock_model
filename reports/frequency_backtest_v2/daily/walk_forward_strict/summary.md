# V2 daily strict walk-forward summary

- V2 strict calculation layer connected: True
- 中国铝业：usable daily rows: 397; blocked rows: 329; blocked reasons: {'insufficient_training_data': 329}
- 紫金矿业：usable daily rows: 437; blocked rows: 1015; blocked reasons: {'missing_strict_production': 693, 'insufficient_training_data': 322}
- 紫金 strict 产量覆盖季度：2023Q1, 2023Q2, 2023Q3, 2023Q4, 2024Q1, 2024Q2, 2024Q3, 2024Q4, 2025Q1, 2025Q2, 2025Q3, 2025Q4, 2026Q1
- 财务与产量均采用公告日期 backward as-of；没有年度均分、生产 forward-fill 或 proxy 生产。
- 中国铝业：已切换至 V2.1 的 C_profit_anchor_ridge 利润层；因独立 OOS 季度仍很少，gap 信号标记为 research_only_v21_insufficient_oos，raw_signal 仅作诊断，不可交易。
- DEFAULT_PROXY 需求字段逐行标在 data_quality_flag；strict 仅指产量层，不表示需求代理已变为真实观测。
- 重要限制：日/周频会增加估值更新次数，但利润训练样本仍是公告后的季度数据；高频行之间高度相关，不能按行数理解为独立样本或交易有效性。
- 输出为研究回测，不构成投资建议。
