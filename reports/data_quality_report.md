# Data quality report

| Dataset | Rows | Missing rate | Stale | Parse confidence | Warning |
|---|---:|---:|---|---:|---|
| financial_quarterly | 50 | 0.0 | False | 0.0 |  |
| production_quarterly | 25 | 0.0325 | False | 0.8439999999999999 |  |
| chalco_quarterly_features | 25 | 0.42947368421052634 | False | nan |  |
| zijin_quarterly_features | 25 | 0.2866666666666667 | False | nan |  |
| api:stock_601600 | <NA> | <NA> | True | <NA> | HTTPSConnectionPool(host='push2his.eastmoney.com', port=443): Max retries exceeded with url: /api/qt/stock/kline/get?fields1=f1%2Cf2%2Cf3%2Cf4%2Cf5%2Cf6%2Cf7%2Cf8%2Cf9%2Cf10%2Cf11%2Cf12%2Cf13&fields2=f51%2Cf52%2Cf53%2Cf54%2Cf55%2Cf56%2Cf57%2Cf58%2Cf59%2Cf60%2Cf61&beg=20200622&end=20260621&rtntype=6&secid=1.601600&klt=101&fqt=1 (Caused by ProtocolError('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))) |
| api:stock_601899 | <NA> | <NA> | True | <NA> | HTTPSConnectionPool(host='push2his.eastmoney.com', port=443): Max retries exceeded with url: /api/qt/stock/kline/get?fields1=f1%2Cf2%2Cf3%2Cf4%2Cf5%2Cf6%2Cf7%2Cf8%2Cf9%2Cf10%2Cf11%2Cf12%2Cf13&fields2=f51%2Cf52%2Cf53%2Cf54%2Cf55%2Cf56%2Cf57%2Cf58%2Cf59%2Cf60%2Cf61&beg=20200622&end=20260621&rtntype=6&secid=1.601899&klt=101&fqt=1 (Caused by ProtocolError('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))) |
| api:financial_quarterly | <NA> | <NA> | False | <NA> | 50 quarterly records |
| api:china_pmi_monthly | <NA> | <NA> | False | <NA> | 221 rows |
| api:hs300_daily | <NA> | <NA> | True | <NA> | ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) |
| api:quarterly_features | <NA> | <NA> | False | <NA> | chalco=25, zijin=25 |
| api:profit_models | <NA> | <NA> | False | <NA> | [{'company': 'chalco', 'features': ['al_spread', 'alumina_price', 'demand_score', 'is_q4'], 'training_rows': 12, 'status': 'fitted', 'estimator': 'StandardScaler+RidgeCV', 'alpha': 10000.0}, {'company': 'zijin', 'features': ['cu_price', 'au_price_rmb_g', 'cu_au_revenue_index', 'demand_score', 'is_q4'], 'training_rows': 24, 'status': 'fitted', 'estimator': 'StandardScaler+RidgeCV', 'alpha': 1.0}] |
| api:announcement_index | <NA> | <NA> | False | <NA> | 52 periodic reports |
| api:stock_raw_601600 | <NA> | <NA> | False | <NA> | 1564 raw rows through 2026-06-18 00:00:00 |
| api:stock_raw_601899 | <NA> | <NA> | False | <NA> | 1564 raw rows through 2026-06-18 00:00:00 |
| api:stock_raw_000300 | <NA> | <NA> | False | <NA> | 1564 raw rows through 2026-06-18 00:00:00 |
| api:production_quarterly | <NA> | <NA> | False | <NA> | 51 parsed rows |
| financial:revenue_cum | 50 | 0.0 | False | <NA> |  |
| financial:net_profit_cum | 50 | 0.0 | False | <NA> |  |
| financial:eps_cum | 50 | 0.0 | False | <NA> |  |
| financial:announcement_date | 50 | 0.0 | False | <NA> |  |
| financial:revenue_q | 50 | 0.0 | False | <NA> |  |
| financial:net_profit_q | 50 | 0.0 | False | <NA> |  |
| financial:eps_q | 50 | 0.0 | False | <NA> |  |
| financial:attributable_profit | 50 | 0.0 | False | <NA> |  |
| announcement_index | 52 | 0.0 | False | <NA> |  |
| announcement:pdf_download | 52 | 0.019230769230769232 | False | <NA> | some PDF downloads failed |
| macro:PMI | 221 | 0.4 | True | <NA> | missing or older than 10 days |
| macro:HS300 | 0 | 1.0 | True | <NA> | missing or older than 10 days |
| chalco:alumina_2020_2023 | 12 | 0.48 | False | <NA> | AO futures unavailable before 2023-06-19; use SMM API or fallback |
