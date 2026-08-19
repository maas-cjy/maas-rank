#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MaaS Rank —— 榜单数据自动更新脚本
================================================
数据源（均为公开接口，无需密钥）：

  1. LMArena Elo（全球人类盲测 Elo）
     HuggingFace 数据集 lmarena-ai/leaderboard-dataset
     https://datasets-server.huggingface.co/rows?dataset=lmarena-ai/leaderboard-dataset&config=text&split=latest

  2. SuperCLUE 智能指数（中文能力）
     https://www.superclueai.com/data/generalboard/<月份>.xlsx   （例：2026年7月.xlsx）

  3. SuperCLUE 输入 / 输出价格（人民币 · 元/百万 tokens）
     https://www.superclueai.com/data/latency_and_price/<月份>_2.xlsx

用法：
  python scripts/fetch_data.py                 # 默认更新 data/models.json
  python scripts/fetch_data.py --dry-run       # 只打印变更，不写文件

行为设计：
  - 只更新「成功抓取且能匹配到模型」的字段；抓取失败 / 未匹配时保留旧值，
    因此任何数据源挂掉都不会破坏网站。
  - 字段被权威来源更新后，自动移除该字段的 est（估算）标记。
  - 无论抓取成功与否，退出码都为 0（文件读写失败除外），便于 CI 使用。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "models.json"
DIFF_FILE = ROOT / "data" / ".last_update.json"
TIMEOUT = 25

# ---------------------------------------------------------------------------
# 模型别名表：models.json 的 id -> 各数据源中的名称特征（子串匹配，忽略大小写）
# ---------------------------------------------------------------------------
MODEL_ALIASES = {
    "claude-opus-5":      ["claude opus 5", "claude-opus-5", "claude-opus-4-7"],
    "claude-opus-4.8":    ["claude opus 4.8", "claude-opus-4.8"],
    "claude-sonnet-4.6":  ["claude sonnet 4.6", "claude-sonnet-4.6"],
    "gpt-5.5":            ["gpt-5.5", "gpt 5.5"],
    "gpt-5.4":            ["gpt-5.4", "gpt 5.4"],
    "gemini-3.1-pro":     ["gemini-3.1-pro", "gemini 3.1 pro"],
    "gemini-3.5-flash":   ["gemini-3.5-flash", "gemini 3.5 flash"],
    "grok-4.5":           ["grok 4.5", "grok-4.5", "grok-4"],
    "llama-4-maverick":   ["llama 4 maverick", "llama-4-maverick"],
    "qwen3.8-max":        ["qwen3.8-max", "qwen3.8 max"],
    "qwen3.7-max":        ["qwen3.7-max", "qwen3.7 max"],
    "deepseek-v4-pro":    ["deepseek-v4-pro", "deepseek v4 pro"],
    "deepseek-v4-flash":  ["deepseek-v4-flash", "deepseek v4 flash"],
    "kimi-k3":            ["kimi-k3", "kimi k3", "kimi-k2.6"],
    "glm-5.2":            ["glm-5.2", "glm 5.2", "glm-5.1"],
    "doubao-seed-2.1-pro": ["doubao-seed-2.1-pro", "doubao seed 2.1", "doubao-seed-2.0-pro"],
    "ernie-5.1":          ["ernie 5.1", "ernie-5.1", "文心"],
    "mimo-v2.5-pro":      ["mimo-v2.5-pro", "mimo v2.5"],
    "minimax-m3":         ["minimax-m3", "minimax m3"],
    "hunyuan-hy3":        ["hy3", "混元"],
}

# SuperCLUE 已知的发布月份（前端写死的可选项），新月份上线后会更新 JS，因此脚本还会
# 动态往前推月份作为候选，取「最新可用」的一份。
SC_KNOWN_DATES = [
    "2026年7月", "2026年5月", "2026年3月", "2025年度测评", "2025年11月",
    "2025年9月", "2025年7月", "2025年5月", "2025年3月", "2024年12月",
    "2024年10月", "2024年8月", "2024年6月", "2024年4月", "2024年2月",
    "2023年12月", "2023年11月", "2023年10月", "2023年9月",
]

SC_BASE = "https://www.superclueai.com/data"
HF_DS = "https://datasets-server.huggingface.co/rows"


def hf_rows_url(dataset: str, config: str, split: str, offset: int, length: int) -> str:
    import urllib.parse as up

    return (
        f"{HF_DS}?dataset={up.quote(dataset)}&config={up.quote(config)}"
        f"&split={up.quote(split)}&offset={offset}&length={length}"
    )


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def http_get(url: str, retries: int = 2) -> bytes:
    """带重试的 GET，返回原始字节；彻底失败抛异常。"""
    last_err: Exception | None = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (MaaS-Rank updater)"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except Exception as e:  # noqa: BLE001
            last_err = e
            log(f"  ⚠ 第 {i + 1} 次请求失败: {e}")
    raise RuntimeError(f"GET {url} 失败: {last_err}")


def to_num(v) -> float | None:
    """把 Excel / JSON 里的值转成 float；'-'、None、空串返回 None。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("¥", "").replace("$", "")
    if s in ("", "-", "--", "None", "null"):
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


# ---------------------------------------------------------------------------
# 1. LMArena Elo —— HuggingFace datasets-server
# ---------------------------------------------------------------------------
def fetch_lmarena() -> dict[str, float]:
    """返回 {模型名(小写): elo}；失败返回 {}。"""
    log("→ 抓取 LMArena Elo (HuggingFace lmarena-ai/leaderboard-dataset)")
    dataset = "lmarena-ai/leaderboard-dataset"
    out: dict[str, float] = {}
    try:
        offset, page_size = 0, 100
        while True:
            url = hf_rows_url(dataset, "text", "latest", offset, page_size)
            raw = http_get(url)
            data = json.loads(raw)
            rows = data.get("rows", [])
            if not rows:
                break
            for row in rows:
                f = row.get("row", {})
                category = str(f.get("category", "")).lower()
                if category and category != "overall":
                    continue
                name = f.get("model_name") or f.get("model") or f.get("name")
                rating = to_num(f.get("rating") if f.get("rating") is not None else f.get("score"))
                if name and rating is not None:
                    out[str(name).lower().strip()] = rating
            offset += len(rows)
            if len(rows) < page_size:
                break
    except Exception as e:  # noqa: BLE001
        log(f"  ✗ LMArena 抓取失败：{e}（保留旧 Elo）")
        return {}
    log(f"  ✓ 拿到 {len(out)} 个模型的 Elo")
    return out


# ---------------------------------------------------------------------------
# 2/3. SuperCLUE —— 总榜 xlsx + 价格 xlsx
# ---------------------------------------------------------------------------
def sc_candidate_dates(limit: int = 14) -> list[str]:
    """动态候选（从当前月往前推）+ 已知列表，去重保序。"""
    today = date.today()
    dyn = [f"{today.year}年{today.month}月"]
    y, m = today.year, today.month
    for _ in range(limit):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        dyn.append(f"{y}年{m}月")
    seen, out = set(), []
    for d in dyn + SC_KNOWN_DATES:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def sc_load_xlsx(url: str):
    """下载 xlsx 并用 openpyxl 解析；失败返回 None。"""
    import io

    import openpyxl

    try:
        raw = http_get(url)
        if raw[:2] != b"PK":
            log(f"  ⚠ {url} 不是有效 xlsx（可能是 404 页面），跳过")
            return None
        wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
        return wb
    except Exception as e:  # noqa: BLE001
        log(f"  ⚠ 解析失败 {url}: {e}")
        return None


def sheet_to_rows(ws) -> list[list]:
    rows = []
    for row in ws.iter_rows(values_only=True):
        rows.append([cell for cell in row])
    return rows


def fetch_superclue() -> tuple[dict[str, float], dict[str, dict], str]:
    """
    返回 (总榜: {模型名小写: 智能指数}, 价格: {模型名小写: {priceIn, priceOut}}, 数据月份)
    失败时返回空 dict。
    """
    scores: dict[str, float] = {}
    prices: dict[str, dict] = {}
    used_date = ""
    for d in sc_candidate_dates():
        gb_url = f"{SC_BASE}/generalboard/{urllib.parse.quote(d)}.xlsx"
        wb = sc_load_xlsx(gb_url)
        if wb is None:
            continue
        # —— 总榜：取「总排行榜」sheet 的 总分 ——
        try:
            sheet = wb["总排行榜"]
        except KeyError:
            wb.close()
            continue
        for r in sheet_to_rows(sheet)[1:]:
            name, total = (r[1] if len(r) > 1 else None), (r[4] if len(r) > 4 else None)
            t = to_num(total)
            if name and t is not None:
                scores[str(name).strip().lower()] = t
        wb.close()

        # —— 价格：latency_and_price 用 `<月份>_2.xlsx`（前端约定），退化为 _1 / 裸名 ——
        for suffix in ("_2", "_1", ""):
            lp_url = f"{SC_BASE}/latency_and_price/{urllib.parse.quote(d + suffix)}.xlsx"
            wb2 = sc_load_xlsx(lp_url)
            if wb2 is None:
                continue
            sheet2 = wb2[wb2.sheetnames[0]]
            rows2 = sheet_to_rows(sheet2)
            headers = [str(h).lower() if h else "" for h in rows2[0]]
            def col(keyword: str) -> int:
                for i, h in enumerate(headers):
                    if keyword in h:
                        return i
                return -1
            i_in, i_out = col("input"), col("output")
            for r in rows2[1:]:
                name = r[0] if r else None
                if not name:
                    continue
                key = str(name).strip().lower()
                entry = prices.setdefault(key, {})
                if i_in >= 0 and len(r) > i_in:
                    v = to_num(r[i_in])
                    if v is not None:
                        entry["priceIn"] = v
                if i_out >= 0 and len(r) > i_out:
                    v = to_num(r[i_out])
                    if v is not None:
                        entry["priceOut"] = v
            wb2.close()
            break  # 该月份价格文件命中一次即可
        used_date = d
        log(f"  ✓ SuperCLUE 数据月份：{d}（智能指数 {len(scores)} 个，价格 {len(prices)} 个）")
        break
    else:
        log("  ✗ SuperCLUE 所有候选月份均抓取失败（保留旧值）")
    return scores, prices, used_date


# ---------------------------------------------------------------------------
# 合并
# ---------------------------------------------------------------------------
def match_model(src_name: str, mid: str) -> bool:
    """判断数据源模型名是否对应 models.json 中的 id。"""
    n = src_name.lower()
    for alias in MODEL_ALIASES.get(mid, []):
        if alias.lower() in n:
            return True
    return False


def apply_updates(models, elo_map, scores, prices) -> list[str]:
    changed: list[str] = []
    n_elo = n_sc = n_price = 0
    for m in models:
        mid = m["id"]
        # Elo
        hit = False
        for src_name, v in elo_map.items():
            if match_model(src_name, mid):
                new_v = round(v)
                old = m.get("elo")
                if old != new_v:
                    m["elo"] = new_v
                    changed.append(f"{mid}.elo {old}→{new_v}")
                m.get("est", {}).pop("elo", None)
                hit = True
                break
        if hit:
            n_elo += 1

        # SuperCLUE 智能指数
        hit_sc = False
        for src_name, v in scores.items():
            if match_model(src_name, mid):
                new_v = round(v, 2)
                old = m.get("superclue")
                if old != new_v:
                    m["superclue"] = new_v
                    changed.append(f"{mid}.superclue {old}→{new_v}")
                m.get("est", {}).pop("superclue", None)
                hit_sc = True
                break
        if hit_sc:
            n_sc += 1

        # SuperCLUE 价格
        hit_pr = False
        for src_name, e in prices.items():
            if match_model(src_name, mid):
                for field in ("priceIn", "priceOut"):
                    if field in e:
                        new_v = round(e[field], 2)
                        old = m.get(field)
                        if old != new_v:
                            m[field] = new_v
                            changed.append(f"{mid}.{field} {old}→{new_v}")
                        m.get("est", {}).pop(field, None)
                hit_pr = True
                break
        if hit_pr:
            n_price += 1

        # 清理空 est
        if m.get("est") == {}:
            m.pop("est", None)

    log(f"  ✓ 匹配更新：Elo {n_elo} 个模型，中文能力 {n_sc} 个模型，价格 {n_price} 个模型")
    if changed:
        log("  变更明细：")
        for c in changed:
            log(f"    - {c}")
    else:
        log("  数据无变化")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description="MaaS Rank 数据自动更新")
    ap.add_argument("--data", default=str(DATA_FILE), help="models.json 路径")
    ap.add_argument("--dry-run", action="store_true", help="只打印变更不写文件")
    args = ap.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        log(f"✗ 找不到数据文件：{data_path}")
        return 1
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    today = date.today().isoformat()
    diff = {"updated": today, "sources": {}, "changes": []}

    # 1) LMArena
    elo_map = fetch_lmarena()
    diff["sources"]["lmarena"] = {"ok": bool(elo_map), "count": len(elo_map)}

    # 2/3) SuperCLUE
    sc_scores, sc_prices, used_date = fetch_superclue()
    diff["sources"]["superclue"] = {
        "ok": bool(sc_scores),
        "count": len(sc_scores),
        "date": used_date,
    }

    # 合并
    changes = apply_updates(data["models"], elo_map, sc_scores, sc_prices)
    diff["changes"] = changes

    # meta 更新（仅当确有数据变化时，避免空跑产生无意义提交）
    meta = data["meta"]
    if changes:
        meta["updated"] = today
        meta["lastAutoUpdate"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sources_note = []
        if elo_map:
            sources_note.append("Elo 来自 LMArena（HuggingFace 数据集，自动抓取）")
        if sc_scores:
            sources_note.append(f"中文能力/价格来自 SuperCLUE（{used_date} 测评，自动抓取）")
        if sources_note:
            meta["note"] = "榜单数据自动更新：" + "；".join(sources_note) + "；未抓取到的字段保留上次快照。"

    if args.dry_run:
        log(f"（dry-run）共 {len(changes)} 处变更，未写文件。")
        return 0

    tmp = data_path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(data_path)
    with open(DIFF_FILE, "w", encoding="utf-8") as f:
        json.dump(diff, f, ensure_ascii=False, indent=2)
    log(f"✓ 已写入 {data_path}")
    log(f"✓ 已写入变更摘要 {DIFF_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
