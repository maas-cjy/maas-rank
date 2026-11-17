"""官网定价直采：从厂商官方文档页抓取 API 价格，作为 SuperCLUE 价格表的补充/覆盖。

设计原则：
- 官网价优先级最高（priceSource="官网"），抓不到时 SuperCLUE 价格表兜底；
- 单个厂商失败只记日志，不影响其他厂商，也不阻塞每日更新；
- 每个厂商一个 fetch_xxx()，返回 {站内模型id: 条目}；新增厂商照抄即可。

抓取方式分两类：
- HTTP   ：文档页是静态 HTML / Mintlify Markdown（URL + ".md"），纯 requests 即可；
- CHROME ：页面 JS 渲染（如 Mintlify 动态表格组件），用无头 Chrome --dump-dom
  渲染后再解析。GitHub ubuntu runner 自带 Chrome，CI 可直接用。

已接入：
- DeepSeek  https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
  （Docusaurus 静态页；高峰/空闲双时段取高峰刊例价，空闲价与缓存命中价
   写入 note / priceCacheHit）
- 智谱      https://docs.bigmodel.cn/cn/guide/start/pricing.md
  （Mintlify Markdown，纯 HTTP；分段定价取最高档并注明档位区间）
- Kimi      https://platform.kimi.com/docs/pricing/chat
  （Mintlify 动态表格，需无头 Chrome）
"""

import html as _html
import re
import shutil
import subprocess
import tempfile
from datetime import date

from fetch_data import http_get

DEEPSEEK_URL = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
ZHIPU_URL = "https://docs.bigmodel.cn/cn/guide/start/pricing.md"
KIMI_URL = "https://platform.kimi.com/docs/pricing/chat"

# 官方 API 模型名 → 站内模型 id（同一 API 模型可对应多个榜单变体）
MODEL_ID_MAP = {
    # DeepSeek
    "deepseek-flash": ["deepseek-v4.1-flash"],
    "deepseek-v4-pro": ["deepseek-v4-pro", "deepseek-v4-pro preview"],
    # 智谱
    "GLM-5.3": ["glm-5.3"],
    "GLM-5.3-Flash": ["glm-5.3-flash"],
    "GLM-5.2": ["glm-5.2"],
    "GLM-5.1": ["glm-5.1"],
    "GLM-5": ["glm-5"],
    "GLM-4.7": ["glm-4.7"],
    "GLM-4.7-Flash": ["glm-4.7-flash"],
    "GLM-4.5-Air": ["glm-4.5-air"],
    "GLM-4-Plus": ["glm-4-plus"],
    # Kimi
    "kimi-k3.1-pro": ["kimi k3.1 pro"],
    "kimi-k3": ["kimi-k3"],
    "kimi-k2.6": ["kimi-k2.6"],
}


def _make_entry(price_in, price_out, today, note, cache_hit=None, currency="CNY"):
    return {
        "priceIn": None if price_in is None else round(price_in, 2),
        "priceOut": None if price_out is None else round(price_out, 2),
        "priceCacheHit": None if cache_hit is None else round(cache_hit, 2),
        "priceCurrency": currency,
        "priceSource": "官网",
        "priceDate": today,
        "priceNote": note,
    }


# ---------------- DeepSeek（静态 HTML） ----------------

def _cells(row_html: str) -> list[str]:
    """一行 <tr> 里各单元格的纯文本。"""
    out = []
    for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row_html, re.S):
        t = _html.unescape(re.sub(r"<[^>]+>", " ", c))
        t = re.sub(r"\s+", " ", t).strip()
        out.append(t)
    return out


def _parse_deepseek_prices(page_html: str) -> dict[str, dict]:
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
        out[name] = {
            "priceIn": prices["miss_in"]["peak"][i],
            "priceOut": prices["out"]["peak"][i],
            "priceCacheHit": prices["hit_in"]["peak"][i],
            "idlePriceIn": prices["miss_in"]["idle"][i],
            "idlePriceOut": prices["out"]["idle"][i],
        }
    return out


def fetch_deepseek(today: str) -> dict[str, dict]:
    """抓取 DeepSeek 官网价，返回 {站内模型id: 条目}。"""
    body = http_get(DEEPSEEK_URL).decode("utf-8", "replace")
    raw = _parse_deepseek_prices(body)

    entries: dict[str, dict] = {}
    for src_name, p in raw.items():
        ids = MODEL_ID_MAP.get(src_name)
        if not ids:
            continue  # 官网新模型暂未映射，忽略并留待人工接入
        note = (
            f"高峰时段刊例价（空闲时段输入 ¥{p['idlePriceIn']:g}、"
            f"输出 ¥{p['idlePriceOut']:g}）；缓存命中输入 ¥{p['priceCacheHit']:g}"
        )
        entry = _make_entry(p["priceIn"], p["priceOut"], today, note,
                            cache_hit=p["priceCacheHit"])
        for mid in ids:
            entries[mid] = dict(entry)
    return entries


# ---------------- 智谱（Mintlify Markdown，纯 HTTP） ----------------

def _md_price(v: str) -> float | None:
    """Markdown 价格单元格 → 数值；「免费」算 0，其余非数字返回 None。"""
    v = v.strip().replace(",", "")
    if v == "免费":
        return 0.0
    m = re.fullmatch(r"[\d.]+", v)
    return float(v) if m else None


def _parse_zhipu_prices(md: str) -> dict[str, dict]:
    """解析智谱定价 Markdown，返回 {官方模型名: {priceIn, priceOut, priceCacheHit, tiers}}。

    表格行形如：| GLM-5.2 | 1M | 8 | 28 | 限时免费 | 2 |
    列：模型名称 / 上下文 / 输入单价 / 输出单价 / 缓存存储 / 缓存命中。
    同一模型可能有多档（按输入长度/输出长度分段），全部保留供选择档位。
    """
    tiers: dict[str, list] = {}
    for line in md.splitlines():
        line = line.strip()
        if line.startswith(">"):
            line = line.lstrip("> ").strip()
        if not (line.startswith("|") and line.rstrip().endswith("|")):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 6 or not cells[0].startswith("GLM"):
            continue
        if cells[0] == "模型名称":  # 表头
            continue
        pin, pout = _md_price(cells[2]), _md_price(cells[3])
        hit = _md_price(cells[5]) if cells[5] != "不支持" else None
        if pin is None or pout is None:
            continue
        # 智谱 Markdown 会把方括号转义成 \[ \]，展示前还原
        ctx = cells[1].replace("\\[", "[").replace("\\]", "]")
        tiers.setdefault(cells[0], []).append(
            {"priceIn": pin, "priceOut": pout, "priceCacheHit": hit, "ctx": ctx})
    if not tiers:
        raise ValueError("智谱定价 Markdown 未解析出 GLM 价格行（页面结构可能已改版）")
    return tiers


def fetch_zhipu(today: str) -> dict[str, dict]:
    """抓取智谱官网价。分段定价取最高档（保守口径），note 里写明档位区间。"""
    md = http_get(ZHIPU_URL).decode("utf-8", "replace")
    tiers = _parse_zhipu_prices(md)

    entries: dict[str, dict] = {}
    for src_name, rows_ in tiers.items():
        ids = MODEL_ID_MAP.get(src_name)
        if not ids:
            continue
        # 保守口径：取输入+输出之和最大的档位
        best = max(rows_, key=lambda r: r["priceIn"] + r["priceOut"])
        note = None
        if len(rows_) > 1:
            lo = min(rows_, key=lambda r: r["priceIn"] + r["priceOut"])
            note = (f"分段定价共 {len(rows_)} 档（{lo['ctx']}：¥{lo['priceIn']:g}/¥{lo['priceOut']:g} 起），"
                    f"此处取最高档（{best['ctx']}）")
        if best["priceIn"] == 0 and best["priceOut"] == 0:
            note = "官方免费模型" + (f"（{note}）" if note else "")
        entry = _make_entry(best["priceIn"], best["priceOut"], today, note,
                            cache_hit=best["priceCacheHit"])
        for mid in ids:
            entries[mid] = dict(entry)
    return entries


# ---------------- Kimi（Mintlify 动态表格，无头 Chrome） ----------------

_CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome", "google-chrome-stable", "chromium-browser", "chromium",
)


def _chrome_dump(url: str, budget_ms: int = 15000) -> str:
    """无头 Chrome 渲染页面并返回 DOM；找不到浏览器时抛异常。"""
    exe = None
    for cand in _CHROME_CANDIDATES:
        if cand.startswith("/"):
            import os
            if os.path.exists(cand):
                exe = cand
                break
        else:
            exe = shutil.which(cand)
            if exe:
                break
    if not exe:
        raise RuntimeError("未找到 Chrome/Chromium（官网直采 CHROME 源不可用）")
    profile = tempfile.mkdtemp(prefix="maasrank-chrome-")
    try:
        out = subprocess.run(
            [exe, "--headless=new", "--disable-gpu", "--no-sandbox",
             f"--user-data-dir={profile}", f"--virtual-time-budget={budget_ms}",
             "--dump-dom", url],
            capture_output=True, timeout=90, check=True,
        )
        return out.stdout.decode("utf-8", "replace")
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def _parse_kimi_prices(page_html: str) -> dict[str, dict]:
    """解析 Kimi 定价页渲染后的表格，返回 {官方模型名: 价目dict}。

    K3 系列表：名称 / 输入 / 输出 / 缓存命中 / 缓存写入(5min) / 缓存写入(1h)；
    K2 系列表：名称 / 输入 / 输出 / 缓存命中。价格形如「¥13.00 / MTok」。
    """
    result: dict[str, dict] = {}
    for tbl in re.findall(r"<table.*?</table>", page_html, re.S):
        rows = re.findall(r"<tr.*?</tr>", tbl, re.S)
        if len(rows) < 4:
            continue
        header = " ".join(_cells(rows[0]) + _cells(rows[1]))
        if "基础" not in header and "输入" not in header:
            continue
        has_write = "缓存写入" in header
        for r in rows[2:]:
            cells = _cells(r)
            if len(cells) < 4 or not cells[0].startswith("kimi-"):
                continue
            def num(c):
                m = re.search(r"¥([\d.]+)", c)
                return float(m.group(1)) if m else None
            pin, pout, hit = num(cells[1]), num(cells[2]), num(cells[3])
            if pin is None or pout is None:
                continue
            e = {"priceIn": pin, "priceOut": pout, "priceCacheHit": hit}
            if has_write and len(cells) >= 6:
                e["write5m"], e["write1h"] = num(cells[4]), num(cells[5])
            result[cells[0]] = e
    if not result:
        raise ValueError("Kimi 定价页未解析出价格行（页面结构可能已改版或渲染超时）")
    return result


def fetch_kimi(today: str) -> dict[str, dict]:
    """抓取 Kimi 官网价（需无头 Chrome）。"""
    body = _chrome_dump(KIMI_URL)
    raw = _parse_kimi_prices(body)

    entries: dict[str, dict] = {}
    for src_name, p in raw.items():
        ids = MODEL_ID_MAP.get(src_name)
        if not ids:
            continue
        note = f"缓存命中输入 ¥{p['priceCacheHit']:g}/M" if p.get("priceCacheHit") is not None else None
        if p.get("write5m") is not None:
            note = (note + "；" if note else "") + \
                f"缓存写入（5min TTL）¥{p['write5m']:g}/M、（1h TTL）¥{p['write1h']:g}/M"
        entry = _make_entry(p["priceIn"], p["priceOut"], today, note,
                            cache_hit=p.get("priceCacheHit"))
        for mid in ids:
            entries[mid] = dict(entry)
    return entries


# ---------------- 汇总 ----------------

SOURCES = [
    ("deepseek", fetch_deepseek),
    ("zhipu", fetch_zhipu),
    ("kimi", fetch_kimi),
]


def fetch_all(today: str | None = None) -> tuple[dict[str, dict], list[dict]]:
    """抓取全部已接入厂商的官网价。

    返回（{站内模型id: 条目}, 各源状态列表）。单个源失败不影响其他源，
    状态里带 error 信息供日志记录。
    """
    if today is None:
        t = date.today()
        today = f"{t.year}年{t.month}月{t.day}日"
    merged: dict[str, dict] = {}
    reports: list[dict] = []
    for name, fn in SOURCES:
        try:
            entries = fn(today)
            merged.update(entries)
            reports.append({"source": name, "ok": True, "count": len(entries), "error": None})
        except Exception as e:  # noqa: BLE001
            reports.append({"source": name, "ok": False, "count": 0, "error": str(e)})
    return merged, reports


if __name__ == "__main__":
    import json
    import sys

    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    t = date.today()
    merged, reports = fetch_all()
    for r in reports:
        tag = "✓" if r["ok"] else "✗"
        print(f"{tag} {r['source']}: {r['count']} 条" + (f"｜{r['error']}" if r["error"] else ""))
    print(json.dumps(merged, ensure_ascii=False, indent=2))
