# V2 自动化配置

所有密钥只能在 GitHub Actions Secrets 或本地环境变量中配置，严禁写入代码或报告。

| Secret | 用途 | 缺失时的行为 |
|---|---|---|
| `FRED_API_KEY` | DFII10、DGS10、美元指数、USD/CNY | 标记 `MISSING_FRED_API_KEY`，不伪造宏观数据 |
| `WGC_COOKIE` | WGC 黄金 ETF 下载 | 读取 cache；没有 cache 时标记 `MISSING_WGC_DATA` |
| `SMM_TOKEN` / `MYSTEEL_TOKEN` / `BAICHUAN_TOKEN` | 氧化铝现货、阳极、煤、铝土矿、电价等 | 标记 `BLOCKED_NEEDS_PAID_DATA` |
| `CNINFO_USER_AGENT` | 巨潮公告与 PDF 审计 | 失败时保留已有公告/PDF cache 并记录状态 |

工作流 UTC 时间：daily 10:30（北京时间 18:30）、weekly 周五 12:00、monthly 每月 1 日 11:30、quarterly 每周一 12:00。季度任务只刷新披露数据和审计；模型重训必须另行批准。
