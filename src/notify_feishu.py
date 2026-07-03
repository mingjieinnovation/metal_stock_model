from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import hmac
import json
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

import requests



def _load_local_env_files() -> None:
    """Load .env.local/.env for direct local CLI usage without overriding env vars."""
    for env_path in (Path(".env.local"), Path(".env")):
        if not env_path.exists():
            continue
        for raw in env_path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_local_env_files()

REPORT_DIR = Path("reports")
LOG_CSV = REPORT_DIR / "feishu_notify_log.csv"
LOG_MD = REPORT_DIR / "feishu_notify_log.md"
QUALITY_GATE_CSV = REPORT_DIR / "v2_data_quality_gate.csv"
QUALITY_GATE_MD = REPORT_DIR / "v2_data_quality_gate.md"
DECISION_TABLE_CSV = REPORT_DIR / "v2_latest_decision_table.csv"
DAILY_ALERT_MD = REPORT_DIR / "v2_daily_alert.md"
MODEL_UPDATE_LOG_MD = REPORT_DIR / "v2_model_update_log.md"

SAFE_SIGNAL_STATUSES = {
    "valuation_anchor_only",
    "research_only",
    "daily_gap_alert_only",
    "valuation_observation",
    "observation",
}


def build_feishu_sign(timestamp: str, secret: str) -> str:
    """Build Feishu custom bot signature using the official HMAC rule."""
    string_to_sign = f"{timestamp}\n{secret}"
    return base64.b64encode(
        hmac.new(
            string_to_sign.encode("utf-8"),
            b"",
            digestmod=hashlib.sha256,
        ).digest()
    ).decode("utf-8")


@contextmanager
def _without_unreachable_loopback_proxy():
    """Temporarily bypass the known-dead local proxy used by some shells."""
    proxy_keys = ("ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "GIT_HTTP_PROXY", "GIT_HTTPS_PROXY")
    removed = {}
    for key in proxy_keys:
        value = os.environ.get(key)
        if not value:
            continue
        parsed = urlparse(value)
        if parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port == 9:
            removed[key] = value
            os.environ.pop(key, None)
    try:
        yield
    finally:
        os.environ.update(removed)


def _keyword_title(title: str) -> str:
    keyword = os.environ.get("FEISHU_KEYWORD", "").strip() or "metal_stock_model"
    if keyword not in title:
        return f"{keyword} {title}"
    return title


def _redact_error(message: str) -> str:
    webhook = os.environ.get("FEISHU_WEBHOOK", "")
    secret = os.environ.get("FEISHU_SECRET", "")
    safe = message or ""
    if webhook:
        safe = safe.replace(webhook, "<FEISHU_WEBHOOK_REDACTED>")
    if secret:
        safe = safe.replace(secret, "<FEISHU_SECRET_REDACTED>")
    safe = re.sub(r"https://open\.larksuite\.com/open-apis/bot/v2/hook/[A-Za-z0-9-]+", "<FEISHU_WEBHOOK_REDACTED>", safe)
    return safe[:500]


def post_feishu_text(text: str) -> dict:
    """Post a Feishu text message. Missing webhook is a non-fatal skip."""
    webhook = os.environ.get("FEISHU_WEBHOOK", "").strip()
    secret = os.environ.get("FEISHU_SECRET", "").strip()

    if not webhook:
        message = "FEISHU_WEBHOOK_MISSING: skip Feishu notification"
        print(message)
        print("FEISHU_WEBHOOK_SET=False")
        return {
            "send_status": "skipped",
            "http_status": "",
            "error_message": message,
            "webhook_set": False,
        }

    print("FEISHU_WEBHOOK_SET=True")
    payload: dict[str, Any] = {
        "msg_type": "text",
        "content": {"text": text},
    }
    if secret:
        timestamp = str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = build_feishu_sign(timestamp, secret)

    try:
        with _without_unreachable_loopback_proxy():
            response = requests.post(webhook, json=payload, timeout=15)
        send_status = "sent" if 200 <= response.status_code < 300 else "failed"
        error_message = "" if send_status == "sent" else _redact_error(response.text)
        return {
            "send_status": send_status,
            "http_status": response.status_code,
            "error_message": error_message,
            "webhook_set": True,
        }
    except requests.RequestException as exc:
        return {
            "send_status": "failed",
            "http_status": "",
            "error_message": _redact_error(str(exc)),
            "webhook_set": True,
        }


def should_send_trading_signal(quality_status: str, company: str) -> bool:
    """Return whether an observation/trading-like signal is allowed.

    China Aluminum is never allowed to emit tradable signals in this project.
    Zijin requires a PASS quality gate; proxy-ratio breaches are represented by
    the gate not passing.
    """
    status = (quality_status or "").strip().upper()
    company_name = (company or "").strip().lower()
    if status != "PASS":
        return False
    if "中国铝" in company or "中铝" in company or "chalco" in company_name or "601600" in company_name:
        return False
    if "紫金" in company or "zijin" in company_name or "601899" in company_name:
        return True
    return False


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "pass", "passed"}


def _load_quality_rows() -> list[dict[str, str]]:
    rows = _read_csv_rows(QUALITY_GATE_CSV)
    if rows:
        return rows
    return []


def detect_quality_status() -> str:
    rows = _load_quality_rows()
    if not rows:
        return "WARNING"
    if any(not _truthy(row.get("passed", "")) for row in rows):
        return "FAIL"
    flags = " ".join(row.get("data_quality_flag", "") for row in rows).upper()
    if any(token in flags for token in ["CACHE", "FALLBACK", "BLOCKED", "DEFAULT_PROXY", "MISSING", "WARNING"]):
        return "WARNING"
    return "PASS"


def _quality_reason_counts() -> dict[str, int]:
    rows = _load_quality_rows()
    counts = {"CACHE_USED": 0, "FALLBACK_USED": 0, "BLOCKED": 0, "DEFAULT_PROXY": 0}
    for row in rows:
        flag = row.get("data_quality_flag", "").upper()
        if "CACHE" in flag:
            counts["CACHE_USED"] += 1
        if "FALLBACK" in flag:
            counts["FALLBACK_USED"] += 1
        if "BLOCKED" in flag or not _truthy(row.get("passed", "")):
            counts["BLOCKED"] += 1
        if "DEFAULT_PROXY" in flag or "PROXY_RATIO" in flag:
            counts["DEFAULT_PROXY"] += 1
    return counts


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _decision_rows_by_company() -> dict[str, dict[str, str]]:
    rows = _read_csv_rows(DECISION_TABLE_CSV)
    return {row.get("company", ""): row for row in rows}


def _company_row(names: list[str]) -> dict[str, str]:
    rows = _decision_rows_by_company()
    for company, row in rows.items():
        if any(name in company for name in names):
            return row
    return {}


def _fmt(value: Any, fallback: str = "") -> str:
    text = "" if value is None else str(value)
    if text.lower() == "nan":
        return fallback
    return text or fallback




def _feishu_plain_text(text: str) -> str:
    """Make report text safer for Feishu text messages.

    Feishu text messages auto-link bare markdown-looking filenames such as
    v2_data_quality_gate.md. Use a full-width dot to keep the path readable
    without turning it into a misleading external URL.
    """
    safe = text.replace(".md", "．md")
    safe = safe.replace("tradable_signal", "交易信号")
    return safe


def _read_daily_alert_rows() -> list[dict[str, str]]:
    """Parse the markdown daily alert table into dictionaries."""
    if not DAILY_ALERT_MD.exists():
        return []
    lines = DAILY_ALERT_MD.read_text(encoding="utf-8-sig").splitlines()
    table_lines = [line.strip() for line in lines if line.strip().startswith("|")]
    if len(table_lines) < 3:
        return []
    headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < len(headers):
            cells.extend([""] * (len(headers) - len(cells)))
        rows.append(dict(zip(headers, cells)))
    return rows


def _daily_alert_row(names: list[str]) -> dict[str, str]:
    for row in _read_daily_alert_rows():
        company = row.get("company", "")
        if any(name in company for name in names):
            return row
    return {}


def _format_price(value: Any) -> str:
    text = _fmt(value, "unavailable")
    try:
        return f"{float(text):.2f}"
    except ValueError:
        return text


def _build_price_snapshot_message(message_type: str, quality_status: str) -> str:
    zijin = _daily_alert_row(["紫金"])
    chalco = _daily_alert_row(["中国铝", "中铝"])
    lines = [
        _keyword_title(f"价格预测｜{_today()}｜{message_type}"),
        f"紫金国际：预测价 {_format_price(zijin.get('predicted_price'))} / 实际股价 {_format_price(zijin.get('actual_price'))} / 日期 {_fmt(zijin.get('data_as_of'), 'unavailable')}",
        f"中国铝业：预测价 {_format_price(chalco.get('predicted_price'))} / 实际股价 {_format_price(chalco.get('actual_price'))} / 日期 {_fmt(chalco.get('data_as_of'), 'unavailable')}",
    ]
    if quality_status.upper() != "PASS":
        lines.append(f"质量门禁：{quality_status}；本次不发送交易信号，仅 research / alert")
    return _feishu_plain_text("\n".join(lines))

def _build_quality_alarm() -> str:
    counts = _quality_reason_counts()
    return "\n".join(
        [
            _keyword_title(f"数据质量报警｜{_today()}"),
            "",
            "质量门禁：FAIL",
            "",
            "原因：",
            f"- CACHE_USED: {counts['CACHE_USED']}",
            f"- FALLBACK_USED: {counts['FALLBACK_USED']}",
            f"- BLOCKED: {counts['BLOCKED']}",
            f"- DEFAULT_PROXY: {counts['DEFAULT_PROXY']}",
            "",
            "处理：",
            "- 本次不发送交易信号",
            "- 只保留 research / alert",
            "- 请检查：reports -> v2_data_quality_gate.md",
        ]
    )


def _build_daily_message(quality_status: str) -> str:
    zijin = _company_row(["紫金"])
    chalco = _company_row(["中国铝", "中铝"])
    zijin_signal = _fmt(zijin.get("signal_status"), "research_only")
    chalco_signal = _fmt(chalco.get("signal_status"), "valuation_anchor_only")
    if not should_send_trading_signal(quality_status, "紫金矿业") and zijin_signal not in SAFE_SIGNAL_STATUSES:
        zijin_signal = "research_only"
    if chalco_signal not in {"valuation_anchor_only", "research_only", "daily_gap_alert_only"}:
        chalco_signal = "valuation_anchor_only"
    return "\n".join(
        [
            _keyword_title(f"日报｜{_today()}"),
            "",
            f"质量门禁：{quality_status}",
            "",
            "紫金矿业：",
            f"- 最新价格：{_fmt(zijin.get('actual_price'))}",
            f"- 模型区间 / gap：{_fmt(zijin.get('model_price_or_range'))} / {_fmt(zijin.get('gap'))}",
            f"- 信号状态：{zijin_signal}",
            f"- 数据质量：score={_fmt(zijin.get('data_quality_score'))}; proxy_ratio={_fmt(zijin.get('proxy_ratio'))}",
            "",
            "中国铝业：",
            f"- 最新价格：{_fmt(chalco.get('actual_price'))}",
            f"- Bear/Base/Bull：{_fmt(chalco.get('model_price_or_range'))}",
            f"- 所在区间：{_fmt(chalco.get('price_zone'))}",
            f"- 信号状态：{chalco_signal}",
            f"- 数据质量：score={_fmt(chalco.get('data_quality_score'))}; proxy_ratio={_fmt(chalco.get('proxy_ratio'))}",
            "",
            "报告：",
            "- reports/v2_daily_alert.md",
            "- reports/v2_latest_decision_table.md",
        ]
    )


def _build_weekly_message(quality_status: str, report_paths: list[str]) -> str:
    paths = report_paths or ["reports/v2_weekly_signal.md", "reports/v2_latest_decision_table.md"]
    counts = _quality_reason_counts()
    return "\n".join(
        [
            _keyword_title(f"周报｜{_today()}"),
            "",
            f"质量门禁：{quality_status}",
            "紫金周度观察：请查看周度报告与最新决策表。",
            "中国铝业周度观察：仅保留估值锚和研究观察。",
            f"本周新增 CACHE / FALLBACK / BLOCKED：{counts['CACHE_USED']} / {counts['FALLBACK_USED']} / {counts['BLOCKED']}",
            "报告路径：",
            *[f"- {path}" for path in paths],
        ]
    )


def _build_monthly_message(quality_status: str, report_paths: list[str]) -> str:
    paths = report_paths or ["reports/v2_monthly_valuation.md", "reports/v2_latest_decision_table.md"]
    allow_zijin = should_send_trading_signal(quality_status, "紫金矿业")
    return "\n".join(
        [
            _keyword_title(f"月度估值｜{_today()}"),
            "",
            "紫金矿业月度估值：请查看月度估值报告。",
            "中国铝业 Bear/Base/Bull：请查看最新决策表。",
            "数据缺口：请查看 reports/v2_data_gap_dashboard.md。",
            f"是否允许交易信号：{str(allow_zijin)}",
            "报告路径：",
            *[f"- {path}" for path in paths],
        ]
    )


def _build_quarterly_message(quality_status: str, report_paths: list[str]) -> str:
    paths = report_paths or ["reports/v2_data_gap_dashboard.md", "reports/v2_data_quality_gate.md", "reports/v2_latest_decision_table.md"]
    return "\n".join(
        [
            _keyword_title(f"季度检查｜{_today()}"),
            "",
            f"质量门禁：{quality_status}",
            "检查范围：财务披露、生产数据、真实因子覆盖和数据缺口。",
            "输出边界：质量门禁未通过时仅保留 research / alert。",
            "报告路径：",
            *[f"- {path}" for path in paths],
        ]
    )


def _message_for_type(message_type: str, quality_status: str, report_paths: list[str]) -> str:
    """Build the outbound message.

    Current product behavior: send the latest price/prediction snapshot for every schedule.
    Quality gate failures keep the alert header and never include tradable-signal wording.
    """
    return _build_price_snapshot_message(message_type, quality_status)


def post_feishu_report(title: str, summary: str, report_paths: list[str], quality_status: str) -> dict:
    """Build and post a report notification.

    If the quality gate is not PASS, this sends only the data-quality alarm.
    """
    message_type = title.strip().lower() if title else "daily"
    if message_type not in {"daily", "weekly", "monthly", "quarterly", "test"}:
        message_type = "daily"
    text = _message_for_type(message_type, quality_status, report_paths)
    if quality_status.upper() != "PASS":
        text = text.replace("tradable_signal", "交易信号")
    elif summary:
        text = f"{text}\n\n摘要：{summary}"
    return post_feishu_text(text)


def _append_notify_log(message_type: str, quality_status: str, result: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "run_time": datetime.now().isoformat(timespec="seconds"),
        "message_type": message_type,
        "quality_status": quality_status,
        "send_status": str(result.get("send_status", "")),
        "http_status": str(result.get("http_status", "")),
        "error_message": _redact_error(str(result.get("error_message", ""))),
    }
    fieldnames = ["run_time", "message_type", "quality_status", "send_status", "http_status", "error_message"]
    exists = LOG_CSV.exists()
    with LOG_CSV.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(row)
    _write_log_md()


def _write_log_md() -> None:
    rows = _read_csv_rows(LOG_CSV)
    fieldnames = ["run_time", "message_type", "quality_status", "send_status", "http_status", "error_message"]
    lines = ["# Feishu notification log", "", "| " + " | ".join(fieldnames) + " |", "|" + "|".join(["---"] * len(fieldnames)) + "|"]
    for row in rows[-50:]:
        lines.append("| " + " | ".join(_fmt(row.get(name)).replace("|", "/") for name in fieldnames) + " |")
    LOG_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(message_type: str) -> dict:
    quality_status = detect_quality_status()
    report_paths_by_type = {
        "daily": ["reports/v2_daily_alert.md", "reports/v2_latest_decision_table.md"],
        "weekly": ["reports/v2_weekly_signal.md", "reports/v2_latest_decision_table.md"],
        "monthly": ["reports/v2_monthly_valuation.md", "reports/v2_latest_decision_table.md"],
        "quarterly": ["reports/v2_data_gap_dashboard.md", "reports/v2_data_quality_gate.md", "reports/v2_latest_decision_table.md"],
        "test": ["reports/v2_data_quality_gate.md"],
    }
    result = post_feishu_report(
        title=message_type,
        summary="",
        report_paths=report_paths_by_type.get(message_type, []),
        quality_status=quality_status,
    )
    _append_notify_log(message_type, quality_status, result)
    print(json.dumps({
        "message_type": message_type,
        "quality_status": quality_status,
        "send_status": result.get("send_status"),
        "http_status": result.get("http_status"),
        "webhook_set": result.get("webhook_set"),
    }, ensure_ascii=False))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Send metal_stock_model report notification to Feishu custom bot.")
    parser.add_argument("--type", choices=["test", "daily", "weekly", "monthly", "quarterly"], default="daily")
    args = parser.parse_args()
    run(args.type)


if __name__ == "__main__":
    main()





