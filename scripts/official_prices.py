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
- Anthropic https://platform.claude.com/docs/en/models/fable-5/overview
  （Next.js 动态页，需无头 Chrome；一页全系表格）
- 阿里百炼  https://help.aliyun.com/zh/model-studio/billing-for-model-studio
  （纯 HTTP 静态 HTML；价格表分散在数十个分表中，需按表头过滤国际版/
   音频/图像表，模型单元格有 rowspan 跨行档位，输出列可能拆「非思考/思考」）
- MiniMax   https://platform.minimaxi.com/document/price
  （纯 HTTP 静态 HTML；划线价 <del>原价</del> 折后价取折后，「标准/优先」
   tab 两套表并存取高者，保守口径）
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
            note = "官方限时免费（恢复收费请以官网现价为准）" + (f"（{note}）" if note else "")
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
             # 本机系统代理未启动时 Chrome 会 ERR_PROXY_CONNECTION_FAILED，
             # 强制直连（CI runner 本就是直连，无副作用）
             "--proxy-server=direct://", "--proxy-bypass-list=*",
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


# ---------------- Anthropic（Next.js 动态页，无头 Chrome 渲染一页全表） ----------------

ANTHROPIC_URL = "https://platform.claude.com/docs/en/models/fable-5/overview"

# 官方模型页表格名 → 站内模型 id（官网在售款；下架旧款不在官网表中，保持「未收录」）
ANTHROPIC_NAME_MAP = {
    "claude fable 5": ["claude-fable-5"],
    "claude opus 5.5": ["claude-opus-5.5"],
    "claude sonnet 5.5": ["claude-sonnet-5.5"],
    "claude haiku 5.5": ["claude haiku 5.5"],
}


def fetch_anthropic(today: str) -> dict[str, dict]:
    """抓取 Anthropic 官方模型页价格表（需无头 Chrome）。

    表形如：Model | Context | Max output | Price / MTok | …
    Price 列为 "$8 / $40"（输入/输出，$/MTok），阶梯价带 "From" 前缀。
    """
    body = _chrome_dump(ANTHROPIC_URL)
    entries: dict[str, dict] = {}
    for table in re.findall(r"<table.*?</table>", body, re.S):
        for row in re.findall(r"<tr.*?</tr>", table, re.S):
            cells = _cells(row)
            if len(cells) < 4 or not cells[0] or cells[0].lower() == "model":
                continue
            # Legacy 标注内嵌在名称单元格里（如 "Claude Fable 5This modelLegacy"）
            name = re.sub(r"This model.*$", "", cells[0]).strip()
            m = re.match(r"(?:From\s+)?\$([\d.]+)\s*/\s*\$([\d.]+)", cells[3])
            if not m:
                continue
            ids = ANTHROPIC_NAME_MAP.get(name.lower())
            if not ids:
                continue
            note = "官方美元定价（$/百万tokens，标准档）"
            if cells[3].strip().lower().startswith("from"):
                note = "官方美元定价为阶梯价，此处取起步档"
            for mid in ids:
                entries[mid] = _make_entry(float(m.group(1)), float(m.group(2)),
                                           today, note, currency="USD")
    if not entries:
        raise ValueError("Anthropic 模型页未解析出价格行（页面结构可能已改版或渲染超时）")
    return entries


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


# ---------------- 阿里百炼（静态 HTML，数十个分表） ----------------

ALIYUN_URL = "https://help.aliyun.com/zh/model-studio/billing-for-model-studio"

# 官方 Model ID → 站内模型 id（只映射在售商业款；带日期快照/preview/latest 不映射）
ALIYUN_NAME_MAP = {
    "qwen3.8-max": ["qwen3.8-max"],
    "qwen3.7-max": ["qwen3.7-max"],
    "qwen3.7-plus": ["qwen3.7-plus"],
    "qwen3.6-plus": ["qwen3.6-plus"],
    "qwen3.5-flash": ["qwen3.5-flash"],
    "qwen-plus": ["qwen-plus"],
    "qwen3.8-27b": ["qwen3.8-27b"],
    "qwen3.5-397b-a17b": ["qwen3.5-397b-a17b"],
    "qwen3.5-122b-a10b": ["qwen3.5-122b-a10b"],
    "qwen3.5-27b": ["qwen3.5-27b"],
    "qwen3.5-35b-a3b": ["qwen3.5-35b-a3b"],
}


def _parse_aliyun_prices(page_html: str) -> dict[str, list]:
    """解析百炼计费页，返回 {官方 Model ID: [{priceIn, priceOut, tier, discount}]}。

    页面把各产品线价格拆成数十个分表，同一份数据在页内还会重复出现一遍。
    过滤规则：跳过带「服务部署范围」（国际版）、「音频/图片」（按量非 token 计价）
    的表头；正文行首格是 Model ID（可能带 rowspan 跨多条档位行），续行只有
    档位+价格，靠 current_model 接力。价格单元格形如「10 元」或
    「原价 2 元 （限时 8 折）」；输出列可能拆「非思考/思考模式」两列（取高者）。
    """
    tiers: dict[str, list] = {}
    for tbl in re.findall(r"<table.*?</table>", page_html, re.S):
        rows_html = re.findall(r"<tr.*?</tr>", tbl, re.S)
        if len(rows_html) < 2:
            continue
        header = " ".join(_cells(rows_html[0]))
        if ("服务部署范围" in header or "音频" in header or "图片" in header
                or "每百万" not in header):
            continue
        current_model = None
        for row_html in rows_html[1:]:
            cells = _cells(row_html)
            if not cells:
                continue
            m = re.match(r"(qwen[a-z0-9.-]+)", cells[0])
            if m:
                current_model = m.group(1)
                rest = cells[1:]
            elif current_model:
                rest = cells  # 模型格 rowspan 的档位续行
            else:
                continue
            if current_model not in ALIYUN_NAME_MAP:
                continue
            prices, discount = [], None
            for c in rest:
                pm = re.search(r"([\d.]+)\s*元", c)
                if pm:
                    prices.append(float(pm.group(1)))
                    dm = re.search(r"([\d.]+)\s*折", c)
                    if dm:
                        discount = float(dm.group(1)) / 10
            # 2 价=输入/输出；3 价=输入/非思考输出/思考输出（取高者，保守口径）。
            # 其余（omni 的文本/音频四价、免费体验行等）结构不明，跳过不猜。
            if len(prices) not in (2, 3):
                continue
            tier = next((c for c in rest if "Token" in c and ("≤" in c or "阶梯" in c)),
                        None)
            tiers.setdefault(current_model, []).append(
                {"priceIn": prices[0],
                 "priceOut": max(prices[1:]) if len(prices) == 3 else prices[1],
                 "tier": tier, "discount": discount})
    if not tiers:
        raise ValueError("百炼计费页未解析出 Qwen 价格行（页面结构可能已改版）")
    return tiers


def fetch_aliyun(today: str) -> dict[str, dict]:
    """抓取阿里云百炼官网价。多档位取最高档（保守口径），限时折扣取折后价。"""
    body = http_get(ALIYUN_URL).decode("utf-8", "replace")
    tiers = _parse_aliyun_prices(body)

    entries: dict[str, dict] = {}
    for src_name, rows_ in tiers.items():
        ids = ALIYUN_NAME_MAP.get(src_name)
        if not ids:
            continue
        # 统一折算：带限时折扣的档位折算成折后价，并保留原价供 note 说明
        norm: list[dict] = []
        for r in rows_:
            d = r.get("discount")
            if d and d < 1:
                norm.append(dict(r, priceIn=round(r["priceIn"] * d, 2),
                                 priceOut=round(r["priceOut"] * d, 2),
                                 orig=(r["priceIn"], r["priceOut"])))
            else:
                norm.append(r)
        # 保守口径：取输入+输出之和最大的档位
        best = max(norm, key=lambda r: r["priceIn"] + r["priceOut"])
        lo = min(norm, key=lambda r: r["priceIn"] + r["priceOut"])
        note = None
        if len(norm) > 1:
            note = (f"分段定价共 {len(norm)} 档（¥{lo['priceIn']:g}/¥{lo['priceOut']:g} 起），"
                    f"此处取最高档")
        if best.get("orig"):
            note = (f"官方限时 {best['discount'] * 10:g} 折，此处为折后价"
                    f"（原价 ¥{best['orig'][0]:g}/¥{best['orig'][1]:g}）"
                    + (f"；{note}" if note else ""))
        if not note:
            note = "官方刊例价（每百万 tokens）"
        entry = _make_entry(best["priceIn"], best["priceOut"], today, note)
        for mid in ids:
            entries[mid] = dict(entry)
    return entries


# ---------------- MiniMax（静态 HTML，划线价+多 tab 档位） ----------------

MINIMAX_URL = "https://platform.minimaxi.com/document/price"

MINIMAX_NAME_MAP = {
    "MiniMax-M3": ["minimax-m3"],
}


def _parse_minimax_prices(page_html: str) -> dict[str, list]:
    """解析 MiniMax 定价页文本模型表，返回 {基础模型名: [{priceIn, priceOut, priceCacheHit, orig}]}。

    - 单元格形如「<del>6.30</del> 3.15」（永久五折）：划线外数字为现价，取之；
    - 同一模型有「标准 / 优先」两套 tab 表（优先档更贵），两套都收，取高者保守；
    - 只解析表头含「输入价格」「百万 tokens」且不含视频/图片/每秒/每张的表。
    """
    tiers: dict[str, list] = {}
    for tbl in re.findall(r"<table.*?</table>", page_html, re.S):
        rows_html = re.findall(r"<tr.*?</tr>", tbl, re.S)
        if len(rows_html) < 2:
            continue
        header = " ".join(_cells(rows_html[0]))
        if ("输入价格" not in header or "百万" not in header
                or any(k in header for k in ("视频", "图片", "每秒", "每张", "分辨率"))):
            continue
        for row_html in rows_html[1:]:
            raw_cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S)
            if not raw_cells:
                continue
            first = _html.unescape(re.sub(r"<[^>]+>", " ", raw_cells[0])).strip()
            m = re.match(r"(MiniMax-[A-Za-z0-9.-]+)", first)
            if not m:
                continue
            name = m.group(1)
            # 价格列：去掉划线价后取第一个数字（=现价）；划线内数字为原价
            vals, orig = [], None
            for c in raw_cells[1:]:
                dm = re.search(r"<del>\s*([\d.]+)", c)
                if dm:
                    orig = float(dm.group(1))
                c_now = re.sub(r"<del>.*?</del>", "", c, flags=re.S)
                pm = re.search(r"([\d.]+)", _html.unescape(re.sub(r"<[^>]+>", " ", c_now)))
                if pm:
                    vals.append(float(pm.group(1)))
            if len(vals) < 2:
                continue
            tiers.setdefault(name, []).append(
                {"priceIn": vals[0], "priceOut": vals[1],
                 "priceCacheHit": vals[2] if len(vals) > 2 else None, "orig": orig})
    if not tiers:
        raise ValueError("MiniMax 定价页未解析出文本模型价格行（页面结构可能已改版）")
    return tiers


def fetch_minimax(today: str) -> dict[str, dict]:
    """抓取 MiniMax 官网价。标准/优先多档取最高档（保守口径），折扣取折后价。"""
    body = http_get(MINIMAX_URL).decode("utf-8", "replace")
    tiers = _parse_minimax_prices(body)

    entries: dict[str, dict] = {}
    for src_name, rows_ in tiers.items():
        ids = MINIMAX_NAME_MAP.get(src_name)
        if not ids:
            continue
        best = max(rows_, key=lambda r: r["priceIn"] + r["priceOut"])
        lo = min(rows_, key=lambda r: r["priceIn"] + r["priceOut"])
        note = None
        if len(rows_) > 1:
            note = (f"多档位定价（最低档 ¥{lo['priceIn']:g}/¥{lo['priceOut']:g}），"
                    f"此处取最高档")
        if best.get("orig"):
            note = (f"官方永久五折，此处为折后价（原价 ¥{best['orig']:g} 起）"
                    + (f"；{note}" if note else ""))
        if not note:
            note = "官方刊例价（每百万 tokens）"
        entry = _make_entry(best["priceIn"], best["priceOut"], today, note,
                            cache_hit=best.get("priceCacheHit"))
        for mid in ids:
            entries[mid] = dict(entry)
    return entries


# ---------------- 汇总 ----------------

SOURCES = [
    ("deepseek", fetch_deepseek),
    ("zhipu", fetch_zhipu),
    ("kimi", fetch_kimi),
    ("anthropic", fetch_anthropic),
    ("aliyun", fetch_aliyun),
    ("minimax", fetch_minimax),
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
