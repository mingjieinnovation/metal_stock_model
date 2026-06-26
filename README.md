# metal_stock_model

自动化的中国铝业（`601600.SH`）与紫金矿业（`601899.SH`）研究管道。API 是主数据源；本地 API cache 是第二优先级；`data/fallback/` 只在 API 和 cache 都不可用时使用。每个阶段独立容错，并将来源、陈旧度、缺失率与 PDF 解析置信度写进数据质量报告。

## English version / Portfolio demo

- English overview: [`README.en.md`](README.en.md)
- Demo walkthrough: [`docs/demo_guide.md`](docs/demo_guide.md)
- Static demo page: [`index.html`](index.html)
- GitHub Pages URL after deployment: `https://mingjieinnovation.github.io/metal_stock_model/`

这份公开 demo 的定位是 portfolio / research governance 展示页：说明项目如何抓取数据、审计数据质量、分层输出估值/观察/报警，而不是展示可交易信号。

## Portfolio 页面

`index.html` 是可直接部署到 GitHub Pages 的静态介绍页面。它说明项目的数据治理、研究输出边界和运行节奏；页面不包含市场数据、模型权重或可交易信号。公开发布时请保持 `data/` 与 `models/` 被 `.gitignore` 排除。

## 每日运行

```powershell
python -m src.update_daily_market
python -m src.v2_data_quality_gate
python -m src.v2_latest_decision_table
python -m src.v2_model_update_log
```

如需发送飞书通知：

```powershell
python -m src.notify_feishu --type daily
```

产物包括：

- `data/processed/financial_quarterly.parquet`：API 财务累计值转单季度值，净利润统一为亿元。
- `data/processed/production_quarterly.parquet`：巨潮公告 PDF 自动提取的产量；低于 0.7 置信度不会作为可靠训练数据。
- `data/processed/*_quarterly_features.parquet`：季度利润与估值特征。
- `reports/v2_latest_decision_table.md`：最新估值/观察状态、质量降级原因。
- `reports/v2_data_quality_gate.md`：API/cache/fallback、缺失率、陈旧度和 PDF 解析质量。

## 数据优先级

1. API 历史/实时数据；成功后覆盖 API cache。
2. 本地 `data/cache/` API cache。
3. `data/fallback/` 容错文件。
4. 明确标记的 proxy/default。
5. blocked/missing，不静默填充。

氧化铝使用 SHFE AO 主力数据优先；AO 缺失才读取 fallback。PDF 下载失败不影响财务 API 和其他模型步骤。

## 自动更新

GitHub Actions 覆盖：

- daily market refresh
- weekly signal observation
- monthly valuation update
- quarterly fundamental audit
- GitHub Pages demo deployment

市场价格模型使用月度样本：紫金从 2020 年起；中国铝业受 AO 期货 2023-06 上市限制，从 2023-06 起。价格抓取使用不复权日线，避免将复权价误报为实际收盘价。
