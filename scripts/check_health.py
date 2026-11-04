#!/usr/bin/env python3
"""数据源健康度检查。

背景：fetch_data.py 的设计是「抓取失败就沿用上期数据」，好处是不会把榜单写坏，
坏处是数据源断了网站看起来一切正常——2026-09 至 11 月就是这样静默冻结了两个月。

本脚本做两件事：
  1. 汇总各数据源的连续失败次数、数据期新鲜度，写出 data/health.json，
     站点读取后会在页面顶部显示「数据更新延迟」提示条；
  2. --strict 模式下，连续 2 周抓取失败或数据超过 N 天未变化时以非 0 退出，
     让 GitHub Actions 变红（仓库默认会发失败邮件），不再无声无息。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = ROOT / "data"

# 连续失败几次算「真出事」：一次失败可能只是上游临时抖动，连续两次基本可以确认
STALE_FAILURES = 2
# 数据超过多少天没有变化算停更（正常每周都会有些许 Elo 波动）
STALE_DAYS = 14
# 超过多少天没变化开始给黄色预警（不影响退出码）
WARN_DAYS = 8


def log(msg: str) -> None:
    print(msg, flush=True)


def read_json(path: Path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def parse_day(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def superclue_period_months_old(period: str, today: date) -> int | None:
    """把「2026年7月」这类期数换算成距今几个月，用于判断中文榜是否长期未更新。"""
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月", str(period or ""))
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    return (today.year - year) * 12 + (today.month - month)


def build_source(name: str, cur: dict, prev: dict, today: date) -> dict:
    ok = bool(cur.get("ok"))
    prev_fails = int((prev.get(name) or {}).get("consecutive_failures") or 0)
    fails = 0 if ok else prev_fails + 1
    item = {
        "ok": ok,
        "count": cur.get("count", 0),
        "consecutive_failures": fails,
        "last_success": (today.isoformat() if ok
                         else (prev.get(name) or {}).get("last_success")),
    }
    if name == "superclue":
        item["period"] = cur.get("date", "")
        item["period_months_old"] = superclue_period_months_old(cur.get("date", ""), today)
    return item


def main() -> int:
    ap = argparse.ArgumentParser(description="检查榜单数据源健康度")
    ap.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="data 目录路径")
    ap.add_argument("--today", default="", help="指定今天日期（YYYY-MM-DD，测试用）")
    ap.add_argument("--stale-days", type=int, default=STALE_DAYS,
                    help=f"多少天没有数据变化判定为停更（默认 {STALE_DAYS}）")
    ap.add_argument("--strict", action="store_true",
                    help="状态为 stale 时以退出码 1 结束（供 CI 告警）")
    ap.add_argument("--check-only", action="store_true", help="只检查不写 health.json")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    today = parse_day(args.today) or date.today()

    last_update = read_json(data_dir / ".last_update.json", {})
    models = read_json(data_dir / "models.json", {})
    prev_health = read_json(data_dir / "health.json", {})

    cur_sources = last_update.get("sources") or {}
    prev_sources = prev_health.get("sources") or {}

    sources = {
        name: build_source(name, cur_sources.get(name) or {}, prev_sources, today)
        for name in ("lmarena", "superclue")
    }

    data_date = parse_day((models.get("meta") or {}).get("updated"))
    days_since = (today - data_date).days if data_date else None

    reasons: list[str] = []
    for name, label in (("lmarena", "LMArena 竞技场"), ("superclue", "SuperCLUE 中文榜")):
        s = sources[name]
        if s["consecutive_failures"] >= STALE_FAILURES:
            reasons.append(f"{label}已连续 {s['consecutive_failures']} 周抓取失败")

    if days_since is not None and days_since >= args.stale_days:
        reasons.append(f"榜单数据已 {days_since} 天没有变化")

    if reasons:
        status = "stale"
    elif days_since is None or days_since >= WARN_DAYS or any(
        s["consecutive_failures"] >= 1 for s in sources.values()
    ):
        status = "warn"
    else:
        status = "ok"

    if status == "stale":
        head = "；".join(reasons)
        tail = f"当前榜单数据期为 {data_date.isoformat()}，正在核查数据源。" if data_date else "正在核查数据源。"
        message = f"{head}，{tail}"
    elif status == "warn":
        message = f"本期部分数据源抓取异常，已沿用上期数据（数据期 {data_date.isoformat() if data_date else '未知'}）。"
    else:
        message = ""

    health = {
        "checked": today.isoformat(),
        "status": status,
        "stale": status == "stale",
        "data_date": data_date.isoformat() if data_date else None,
        "days_since_update": days_since,
        "sources": sources,
        "message": message,
    }

    if not args.check_only:
        data_dir.mkdir(parents=True, exist_ok=True)
        tmp = (data_dir / "health.json").with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(health, f, ensure_ascii=False, indent=2)
            f.write("\n")
        tmp.replace(data_dir / "health.json")

    # 控制台 / Actions 注解
    log(f"数据健康度：{status}（数据期 {health['data_date']}，距今 {days_since} 天）")
    for name, s in sources.items():
        log(f"  - {name}: ok={s['ok']} 连续失败={s['consecutive_failures']} "
            f"条数={s['count']}" + (f" 期数={s.get('period')}" if s.get("period") else ""))
    if message:
        level = "error" if status == "stale" else "warning"
        log(f"::{level}::{message}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("### 数据源健康度：" + status + "\n\n")
            f.write("| 数据源 | 抓取 | 连续失败 | 数据量 | 备注 |\n|---|---|---|---|---|\n")
            for name, s in sources.items():
                note = s.get("period") or ""
                if s.get("period_months_old") is not None:
                    note += f"（{s['period_months_old']} 个月前）"
                f.write(f"| {name} | {'✓' if s['ok'] else '✗'} | "
                        f"{s['consecutive_failures']} | {s['count']} | {note} |\n")
            f.write(f"\n数据期：{health['data_date']} · 距今 {days_since} 天\n")
            if message:
                f.write(f"\n**{message}**\n")

    if args.strict and status == "stale":
        log("数据源异常已确认，本次任务标记为失败以触发通知。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
