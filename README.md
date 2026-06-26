# metal_stock_model

自动化的中国铝业（`601600.SH`）与紫金矿业（`601899.SH`）研究管道。API 是主数据源；本地 API cache 是第二优先级；`data/fallback/` 只在 API 和 cache 都不可用时使用。每个阶段独立容错，并将来源、陈旧度、缺失率与 PDF 解析置信度写进数据质量报告。


## Portfolio 页面

`index.html` 是可直接部署到 GitHub Pages 的静态介绍页面。它说明项目的数据治理、研究输出边界和运行节奏；页面不包含市场数据、模型权重或可交易信号。公开发布时请保持 `data/` 与 `models/` 被 `.gitignore` 排除。

## 每日运行

```powershell
python -m src.fetch_stock
python -m src.fetch_futures
python -m src.fetch_macro
python -m src.fetch_fundamentals
python -m src.fetch_announcements
python -m src.parse_reports
python -m src.build_features
python -m src.fit_profit_models
python -m src.backtest_models
python -m src.update_daily
python -m src.data_quality
```

产物包括：

- `data/processed/financial_quarterly.parquet`：API 财务累计值转单季度值，净利润统一为亿元。
- `data/processed/production_quarterly.parquet`：巨潮公告 PDF 自动提取的产量；低于 0.7 置信度不会作为可靠训练数据。
- `data/processed/*_quarterly_features.parquet`：季度利润与估值特征。
- `reports/latest_signal.md`：利润预测、目标 PE 动态估值及数据来源。
- `reports/data_quality_report.md`：API/cache/fallback、缺失率、陈旧度和 PDF 解析质量。

## 数据优先级

1. API 历史/实时数据；成功后覆盖 API cache。
2. 本地 `data/cache/` API cache。
3. `data/fallback/` 容错文件。
4. 中性默认值（报告会标记 WARNING）。

氧化铝使用 SHFE AO 主力数据优先；AO 缺失才读取 fallback。PDF 下载失败不影响财务 API 和其他模型步骤。

## 自动更新

GitHub Actions 在工作日北京时间 17:45（UTC 09:45）执行完整流程，并只在有变更时提交 `data/raw`、`data/processed`、`data/cache`、`models` 和 `reports`。


市场价格模型使用月度样本：紫金从 2020 年起；中国铝业受 AO 期货 2023-06 上市限制，从 2023-06 起。价格抓取使用不复权（qt=0）日线，避免将复权价误报为实际收盘价。


