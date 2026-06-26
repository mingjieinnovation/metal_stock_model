# 金属股票模型固定报告

## 阅读方式

- R²/MAE/RMSE 是价格模型的回测拟合指标，不等于因果解释或可交易证明。
- 中铝月度 V2.2 的 TTM R² 单列：0.915 是 full-sample diagnostic；-1.708 是 walk-forward OOS，不能混用。
- 紫金产量使用 strict 可见季度；中铝需求层仍含 DEFAULT_PROXY，煤/电/产量未作为伪造的 strict 数据引入。

## 一、中铝：中国铝业

### 模型与用途

- 月度：`monthly_v22_valuation_anchor`。V2.2 G 使用 TTM/已公告利润锚与商品利润混合；用于估值中枢和持仓判断。
- 周度：`weekly_v22_trading_observation`。使用 V2.1-C 利润锚点 Ridge 的 raw gap 进行 4W/13W/26W 观察；仅与月度同向才可标为 research-only stronger observation。
- 日度：`daily_v22_gap_alert`。同一 C 模型的日度 gap，仅报警，禁止单独生成 tradable signal。
- C 因子：商品价差/氧化铝环境、需求分数、最近已公告利润、TTM 已公告利润、近两季均值和完整季度季节性。

| frequency   | model                    | selected_profit_model   |   n |   mae |   rmse |   mape |   r2_price_model |   corr_price_model |   latest_actual |   latest_model_price |   latest_gap | latest_raw_signal   | signal_status                      |
|:------------|:-------------------------|:------------------------|----:|------:|-------:|-------:|-----------------:|-------------------:|----------------:|---------------------:|-------------:|:--------------------|:-----------------------------------|
| monthly     | v2_1_chalco_profit_model | C_profit_anchor_ridge   |  20 | 2.224 |  2.651 |  0.24  |        -0.217359 |           0.775871 |           11.42 |                9.277 |        0.231 | overvalued          | research_only_v21_insufficient_oos |
| weekly      | v2_1_chalco_profit_model | C_profit_anchor_ridge   |  84 | 2.241 |  2.646 |  0.252 |        -0.279896 |           0.508067 |           10.8  |               11.144 |       -0.031 | neutral             | research_only_v21_insufficient_oos |
| daily       | v2_1_chalco_profit_model | C_profit_anchor_ridge   | 397 | 2.319 |  2.722 |  0.26  |        -0.313424 |           0.489734 |            9.38 |               11.015 |       -0.148 | undervalued         | research_only_v21_insufficient_oos |
### V2.2 月度 TTM 估值锚

|   n |    mae |   rmse |   mape | ttm_full_sample_r2   |   ttm_oos_r2 |   single_quarter_oos_r2 |   latest_model_price |   latest_gap | signal_status                          |
|----:|-------:|-------:|-------:|:---------------------|-------------:|------------------------:|---------------------:|-------------:|:---------------------------------------|
|   6 | 13.687 | 14.685 |  0.104 |                      |       -1.667 |                  -0.269 |                9.447 |        0.209 | research_only_v22_ttm_oos_below_target |
### 中铝因子相对影响

| frequency   | factor                     |   importance_share |   coefficient_mean | meaning                                        | importance_method                       |
|:------------|:---------------------------|-------------------:|-------------------:|:-----------------------------------------------|:----------------------------------------|
| monthly     | alumina_price_q_mean       |              0.201 |              5.264 | 季度平均氧化铝价格：成本压力与氧化铝业务环境代理。                      | mean_abs_standardized_ridge_coefficient |
| monthly     | demand_score_q_mean        |              0.166 |              4.342 | 需求综合分数：库存、电网、NEV、PMI、地产等；其中多项仍是 DEFAULT_PROXY。 | mean_abs_standardized_ridge_coefficient |
| monthly     | last_announced_q_profit_bn |              0.144 |             -3.771 | 最近已公告单季利润：经营利润惯性锚点，仅在公告后可见。                    | mean_abs_standardized_ridge_coefficient |
| monthly     | al_spread_q_mean           |              0.133 |              3.474 | 季度平均铝-氧化铝价差：原铝与氧化铝成本环境的利润代理。                   | mean_abs_standardized_ridge_coefficient |
| monthly     | last_2q_avg_profit_bn      |              0.108 |              2.81  | 最近两季已公告利润均值：降低单季偶然波动。                          | mean_abs_standardized_ridge_coefficient |
| monthly     | is_q2                      |              0.093 |              2.42  | Q2 季节性虚拟变量。                                    | mean_abs_standardized_ridge_coefficient |
| monthly     | is_q4                      |              0.089 |             -2.326 | Q4 季节性虚拟变量。                                    | mean_abs_standardized_ridge_coefficient |
| monthly     | ttm_announced_profit_bn    |              0.041 |             -0.426 | 已公告 TTM 利润：持续盈利能力锚点，仅在公告后可见。                   | mean_abs_standardized_ridge_coefficient |
| monthly     | is_q3                      |              0.012 |             -0.278 | Q3 季节性虚拟变量。                                    | mean_abs_standardized_ridge_coefficient |
| monthly     | is_q1                      |              0.012 |              0.016 | Q1 季节性虚拟变量。                                    | mean_abs_standardized_ridge_coefficient |
| weekly      | alumina_price_q_mean       |              0.219 |              4.947 | 季度平均氧化铝价格：成本压力与氧化铝业务环境代理。                      | mean_abs_standardized_ridge_coefficient |
| weekly      | demand_score_q_mean        |              0.19  |              4.298 | 需求综合分数：库存、电网、NEV、PMI、地产等；其中多项仍是 DEFAULT_PROXY。 | mean_abs_standardized_ridge_coefficient |
| weekly      | al_spread_q_mean           |              0.124 |              2.802 | 季度平均铝-氧化铝价差：原铝与氧化铝成本环境的利润代理。                   | mean_abs_standardized_ridge_coefficient |
| weekly      | last_announced_q_profit_bn |              0.112 |             -2.532 | 最近已公告单季利润：经营利润惯性锚点，仅在公告后可见。                    | mean_abs_standardized_ridge_coefficient |
| weekly      | is_q2                      |              0.104 |              2.353 | Q2 季节性虚拟变量。                                    | mean_abs_standardized_ridge_coefficient |
| weekly      | is_q4                      |              0.091 |             -2.049 | Q4 季节性虚拟变量。                                    | mean_abs_standardized_ridge_coefficient |
| weekly      | last_2q_avg_profit_bn      |              0.086 |              1.944 | 最近两季已公告利润均值：降低单季偶然波动。                          | mean_abs_standardized_ridge_coefficient |
| weekly      | ttm_announced_profit_bn    |              0.039 |             -0.444 | 已公告 TTM 利润：持续盈利能力锚点，仅在公告后可见。                   | mean_abs_standardized_ridge_coefficient |
| weekly      | is_q1                      |              0.022 |             -0.379 | Q1 季节性虚拟变量。                                    | mean_abs_standardized_ridge_coefficient |
| weekly      | is_q3                      |              0.014 |             -0.086 | Q3 季节性虚拟变量。                                    | mean_abs_standardized_ridge_coefficient |
| daily       | alumina_price_q_mean       |              0.221 |              5.018 | 季度平均氧化铝价格：成本压力与氧化铝业务环境代理。                      | mean_abs_standardized_ridge_coefficient |
| daily       | demand_score_q_mean        |              0.194 |              4.411 | 需求综合分数：库存、电网、NEV、PMI、地产等；其中多项仍是 DEFAULT_PROXY。 | mean_abs_standardized_ridge_coefficient |
| daily       | al_spread_q_mean           |              0.121 |              2.744 | 季度平均铝-氧化铝价差：原铝与氧化铝成本环境的利润代理。                   | mean_abs_standardized_ridge_coefficient |
| daily       | last_announced_q_profit_bn |              0.11  |             -2.488 | 最近已公告单季利润：经营利润惯性锚点，仅在公告后可见。                    | mean_abs_standardized_ridge_coefficient |
| daily       | is_q2                      |              0.101 |              2.302 | Q2 季节性虚拟变量。                                    | mean_abs_standardized_ridge_coefficient |
| daily       | is_q4                      |              0.092 |             -2.087 | Q4 季节性虚拟变量。                                    | mean_abs_standardized_ridge_coefficient |
| daily       | last_2q_avg_profit_bn      |              0.084 |              1.905 | 最近两季已公告利润均值：降低单季偶然波动。                          | mean_abs_standardized_ridge_coefficient |
| daily       | ttm_announced_profit_bn    |              0.043 |             -0.562 | 已公告 TTM 利润：持续盈利能力锚点，仅在公告后可见。                   | mean_abs_standardized_ridge_coefficient |
| daily       | is_q1                      |              0.019 |             -0.293 | Q1 季节性虚拟变量。                                    | mean_abs_standardized_ridge_coefficient |
| daily       | is_q3                      |              0.014 |             -0.075 | Q3 季节性虚拟变量。                                    | mean_abs_standardized_ridge_coefficient |

## 二、紫金矿业

### 模型与用途

- 利润模型：`cu_au_revenue_index + revenue_x_demand + is_q4` 的 expanding Ridge。
- 铜金收入指数使用 strict 已公告矿产铜/矿产金产量与当期铜、金价格；收入×需求交互项反映宏观需求状态；Q4 吸收季节性。
- 日/周/月均在财务和 strict 产量公告后 backward as-of 更新。日/周频提高估值刷新次数，不增加独立季度利润样本。

| frequency   | model                          |   n |   mae |   rmse |   mape |   r2_price_model |   corr_price_model |   latest_actual |   latest_model_price |   latest_gap | latest_raw_signal   | signal_status   |
|:------------|:-------------------------------|----:|------:|-------:|-------:|-----------------:|-------------------:|----------------:|---------------------:|-------------:|:--------------------|:----------------|
| monthly     | v2_fundamental_valuation_model |  22 | 3.058 |  3.69  |  0.126 |         0.800691 |           0.958887 |           30.44 |               30.693 |       -0.008 | neutral             | active          |
| weekly      | v2_fundamental_valuation_model |  93 | 2.802 |  3.344 |  0.114 |         0.820233 |           0.962304 |           29.09 |               30.237 |       -0.038 | neutral             | active          |
| daily       | v2_fundamental_valuation_model | 437 | 2.674 |  3.273 |  0.107 |         0.833309 |           0.947685 |           29.69 |               33.671 |       -0.118 | neutral             | active          |
### 紫金因子相对影响

| frequency   | factor              |   importance_share |   coefficient_mean | meaning                                              | importance_method                      |
|:------------|:--------------------|-------------------:|-------------------:|:-----------------------------------------------------|:---------------------------------------|
| monthly     | cu_au_revenue_index |              0.838 |              4.875 | 铜金收入指数：(矿产铜×铜价 + 矿产金×1000×金价)/1e9；产量仅使用 strict 可见季度。 | mean_abs_coefficient_times_feature_std |
| monthly     | is_q4               |              0.082 |             -8.585 | Q4 季节性虚拟变量。                                          | mean_abs_coefficient_times_feature_std |
| monthly     | revenue_x_demand    |              0.079 |              1.893 | 收入指数与需求分数偏离 0.5 的交互项，反映价格/产量环境与需求状态共同变化。             | mean_abs_coefficient_times_feature_std |
| weekly      | cu_au_revenue_index |              0.841 |              4.84  | 铜金收入指数：(矿产铜×铜价 + 矿产金×1000×金价)/1e9；产量仅使用 strict 可见季度。 | mean_abs_coefficient_times_feature_std |
| weekly      | is_q4               |              0.087 |             -8.673 | Q4 季节性虚拟变量。                                          | mean_abs_coefficient_times_feature_std |
| weekly      | revenue_x_demand    |              0.072 |              0.513 | 收入指数与需求分数偏离 0.5 的交互项，反映价格/产量环境与需求状态共同变化。             | mean_abs_coefficient_times_feature_std |
| daily       | cu_au_revenue_index |              0.825 |              4.915 | 铜金收入指数：(矿产铜×铜价 + 矿产金×1000×金价)/1e9；产量仅使用 strict 可见季度。 | mean_abs_coefficient_times_feature_std |
| daily       | is_q4               |              0.113 |            -11.836 | Q4 季节性虚拟变量。                                          | mean_abs_coefficient_times_feature_std |
| daily       | revenue_x_demand    |              0.062 |             -0.248 | 收入指数与需求分数偏离 0.5 的交互项，反映价格/产量环境与需求状态共同变化。             | mean_abs_coefficient_times_feature_std |

## 三、解读边界

- 因子相对影响：中铝 C 使用标准化 Ridge 系数绝对值；紫金使用 `|系数|×特征历史标准差` 归一化。因此它们是模型内部影响代理，不能解释成利润的真实因果贡献。
- 中铝：当前任何日/周/月 gap 仍是研究用途；月度 TTM OOS 未达到 0.7，且独立季度少于 10。
- 紫金：价格回测较稳定，但同样受季度样本数量、生产解析质量与需求代理限制；不构成投资建议。
