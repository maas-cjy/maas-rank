"""官网定价直采：从厂商官方文档页抓取 API 价格，作为 SuperCLUE 价格表的补充/覆盖。

设计原则：
- 官网价优先级最高（priceSource="官网"），抓不到时 SuperCLUE 价格表兜底；
- 任何一家抓取失败只记日志，不阻塞每日更新（价格字段保持上次数据）；
- 每个厂商一个 fetch_xxx()，返回 {官方模型名: 条目}，再经 MODEL_ID_MAP
  映射到站内模型 id；新增厂商照抄这个模式即可。

已接入：
- DeepSeek  https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
  （Docusaurus 静态页，表格可直接解析；高峰/空闲双时段取高峰刊例价，
   空闲价与缓存命中价写入 note / priceCacheHit）
"""

import html as _html
import re
from datetime import date

from fetch_data import http_get

DEEPSEEK_URL = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"

# 官方 API 模型名 → 站内模型 id（同一 API 模型可对应多个榜单变体）
MODEL_ID_MAP = {
    "deepseek-flash": ["deepseek-v4.1-flash"],
    "deepseek-v4-pro": ["deepseek-v4-pro", "deepseek-v4-pro preview"],
}


def _cells(row_html: str) -> list[str]:
    """一行 <tr> 里各单元格的纯文本。"""
    out = []
    for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row_html, re.S):
        t = _html.unescape(re.sub(r"<[^>]+>", " ", c))
        t = re.sub(r"\s+", " ", t).strip()
        out.append(t)
    return out


def _parse_deeseek_prices(page_html: str) -> dict[str, dict]:
    """解析 DeepSeek 定价页主表，返回 {官方模型名: 价目dict}。

    表格结构（Docusaurus，含 rowspan）：表头第一行列出模型名（按列序），
    价格区按「百万tokens输入（缓存命中/未命中）/百万tokens输出」×
    「空闲时段/高峰时段」分块；每行末尾 N 个含「元」的单元格对应 N 列模型。
    """
    tables = re.findall(r"<table.*?</table>", page_html, re.S)
    if not tables:
        raise ValueError("DeepSeek 定价页未找到表格（页面结构可能已改版）")
    rows = [_cells(r) for r in re.findall(r"<tr.*?</tr>", tables[0], re.S)]

    # 表头第一行：'模型' + 各模型 API 名
    models: list[str] = []
    for c in rows[0][1:]:
        name = re.sub(r"\(\d+\)", "", c).strip()  # 去掉脚注序号如 deepseek-flash(1)
        if name:
            models.append(name)
    if not models:
        raise ValueError("DeepSeek 定价页表头未解析出模型名")

    n = len(models)
    prices: dict[str, dict[str, list[float]]] = {}
    cat = None  # hit_in / miss_in / out

    for cells in rows:
        # 官方页面的标签里可能混入空格/换行（如「百万tokens输入 （缓存命中）」），
        # 匹配时先去掉全部空白；价格提取仍用原单元格。
        key = re.sub(r"\s+", "", " ".join(cells))
        if "百万tokens输入（缓存命中）" in key:
            cat = "hit_in"
        elif "百万tokens输入（缓存未命中）" in key:
            cat = "miss_in"
        elif "百万tokens输出" in key:
            cat = "out"
        if cat is None:
            continue
        nums = [c for c in cells if re.fullmatch(r"[\d.]+元", c)]
        if not nums:
            continue
        slot = "peak" if "高峰时段" in key else "idle"
        vals = [float(x.rstrip("元")) for x in nums]
        if len(vals) != n:
            raise ValueError(f"价格列数 {len(vals)} 与模型数 {n} 不符：{cells}")
        prices.setdefault(cat, {})[slot] = vals

    need = {"hit_in", "miss_in", "out"}
    if not need <= set(prices) or not all(
        {"peak", "idle"} <= set(v) for v in prices.values()
    ):
        raise ValueError(f"DeepSeek 价格区解析不完整：{sorted(prices)}")

    out: dict[str, dict] = {}
    for i, name in enumerate(models):
        e = prices
        out[name] = {
            "priceIn": e["miss_in"]["peak"][i],
            "priceOut": e["out"]["peak"][i],
            "priceCacheHit": e["hit_in"]["peak"][i],
            "idlePriceIn": e["miss_in"]["idle"][i],
            "idlePriceOut": e["out"]["idle"][i],
        }
    return out


def fetch_deepseek(today: str) -> tuple[dict[str, dict], list[str]]:
    """抓取 DeepSeek 官网价，返回（站内模型id→条目, 变更说明列表）。"""
    body = http_get(DEEPSEEK_URL).decode("utf-8", "replace")
    raw = _parse_deeseek_prices(body)

    entries: dict[str, dict] = {}
    for src_name, p in raw.items():
        ids = MODEL_ID_MAP.get(src_name)
        if not ids:
            continue  # 官网新模型暂未映射，忽略并留待人工接入
        note = (
            f"高峰时段刊例价（空闲时段输入 ¥{p['idlePriceIn']:g}、"
            f"输出 ¥{p['idlePriceOut']:g}）；缓存命中输入 ¥{p['priceCacheHit']:g}"
        )
        entry = {
            "priceIn": round(p["priceIn"], 2),
            "priceOut": round(p["priceOut"], 2),
            "priceCacheHit": round(p["priceCacheHit"], 2),
            "priceCurrency": "CNY",
            "priceSource": "官网",
            "priceDate": today,
            "priceNote": note,
        }
        for mid in ids:
            entries[mid] = dict(entry)
    return entries, [f"{k} → {v}" for k, v in raw.items()]


def fetch_all(today: str | None = None) -> dict[str, dict]:
    """抓取全部已接入厂商的官网价，合并为 {站内模型id: 条目}。

    任一厂商失败抛出异常由调用方兜底（回退 SuperCLUE 表）。
    """
    if today is None:
        t = date.today()
        today = f"{t.year}年{t.month}月{t.day}日"
    merged: dict[str, dict] = {}
    ds_entries, _seen = fetch_deepseek(today)
    merged.update(ds_entries)
    return merged


if __name__ == "__main__":
    import json
    import sys

    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    t = date.today()
    today = f"{t.year}年{t.month}月{t.day}日"
    entries = fetch_all(today)
    print(json.dumps(entries, ensure_ascii=False, indent=2))
