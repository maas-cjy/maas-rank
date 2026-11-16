#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模型对比实测生成器（按月更新）。

对比一组头部模型（默认：Qwen3.8-Max / Kimi K3 / DeepSeek V4 Pro），
生成一篇带六维雷达图（内联 SVG）、Elo 趋势、价格与性价比的对比文章
（articles/compare-YYYY-MM.html），并登记进 data/articles.json。

用法：
    python scripts/gen_compare_article.py           # 生成并发布
    python scripts/gen_compare_article.py --draft   # 生成草稿（不进 sitemap，列表页不显示）

数据每周更新后重跑一次，对比数据自动刷新。
"""
import argparse
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://maasrank.com/"

# 对比组合（模型 id），全部需有 dims。2026-11 起 SuperCLUE 采用新口径，
# 旧对象（qwen3.8-max 旧版 / kimi-k3 / deepseek-v4-pro）未参加新基准测评，
# 已换为新口径下的三款代表性模型：国产开源新旗舰 / 国际闭源榜首 / 国产高性价比。
TARGETS = ["kimi k3.1 pro", "gemini-4-argon", "deepseek-v4.1-flash"]
LABELS = {"kimi k3.1 pro": "Kimi K3.1 Pro", "gemini-4-argon": "Gemini 4 Argon",
          "deepseek-v4.1-flash": "DeepSeek V4.1 Flash"}
COLORS = {"kimi k3.1 pro": "#F59E0B", "gemini-4-argon": "#8B5CF6",
          "deepseek-v4.1-flash": "#10B981"}

# 2026-11 新口径维度（与 fetch_data.DIM_KEYS 保持一致）
DIMS = [
    ("math", "数理推理"), ("hallu", "幻觉控制"), ("ifollow", "精确指令遵循"),
    ("coding", "智能体编程"), ("longctx", "超长上下文"),
]


def esc(s):
    return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def load(path, default):
    p = os.path.join(ROOT, path)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def price_cny(m, field):
    """模型价格折算为 ¥：CNY（官方人民币报价）原样，其余（美元）按 $1≈¥7.2。"""
    v = (m or {}).get(field)
    if v is None:
        return None
    return v if (m or {}).get("priceCurrency") == "CNY" else v * 7.2


def cny_val(m, v):
    if v is None:
        return None
    return v if (m or {}).get("priceCurrency") == "CNY" else v * 7.2


def fmt_cny(m, field):
    v = price_cny(m, field)
    if v is None:
        return "—"
    return f"¥{v:.1f}" if v >= 1 else f"¥{v:.2f}"


def fmt_val(v, nd=2):
    return "—" if v is None else f"{v:.{nd}f}"


# ---------------------------------------------------------------- 雷达图
def radar_svg(groups):
    """groups: list of (id, name, color, {dim: value})。返回内联 SVG 雷达图。"""
    W, H, CX, CY, R = 380, 360, 190, 170, 105
    n = len(DIMS)
    grid = [0.25, 0.5, 0.75, 1.0]

    def pt(i, r):
        ang = math.radians(-90 + i * 360 / n)
        return (CX + r * math.cos(ang), CY + r * math.sin(ang))

    parts = []
    # 网格
    for g in grid:
        pts = " ".join(f"{pt(i, R * g)[0]:.1f},{pt(i, R * g)[1]:.1f}" for i in range(n))
        parts.append(f'<polygon points="{pts}" fill="none" stroke="#E2E6F0" stroke-width="1"/>')
    # 轴线
    for i in range(n):
        x, y = pt(i, R)
        parts.append(f'<line x1="{CX}" y1="{CY}" x2="{x:.1f}" y2="{y:.1f}" stroke="#E2E6F0" stroke-width="1"/>')
    # 维度标签
    for i, (dim, label) in enumerate(DIMS):
        x, y = pt(i, R * 1.30)
        anchor = "middle" if abs(x - CX) < 12 else ("start" if x > CX else "end")
        parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="11" fill="#5B6272" text-anchor="{anchor}">{label}</text>'
        )
    # 数值点与多边形
    for gid, name, color, vals in groups:
        pts = " ".join(
            f"{pt(i, R * ((vals.get(dim) or 0) / 100.0))[0]:.1f},{pt(i, R * ((vals.get(dim) or 0) / 100.0))[1]:.1f}"
            for i, (dim, _) in enumerate(DIMS)
        )
        parts.append(f'<polygon points="{pts}" fill="{color}" fill-opacity="0.13" stroke="{color}" stroke-width="2"/>')
        for i, (dim, _) in enumerate(DIMS):
            x, y = pt(i, R * ((vals.get(dim) or 0) / 100.0))
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="{color}"/>')
    # 图例（顶部）
    lg_x = W / 2 - (len(groups) * 88) / 2
    for gi, (gid, name, color, vals) in enumerate(groups):
        lx = lg_x + gi * 88
        parts.append(f'<rect x="{lx:.0f}" y="8" width="12" height="12" rx="2" fill="{color}"/>')
        parts.append(f'<text x="{lx + 17:.0f}" y="18" font-size="11" fill="#2A2F3A">{esc(name)}</text>')
    return (
        f'<div class="cv-chart"><svg viewBox="0 0 {W} {H}" role="img" aria-label="维度能力雷达图">'
        + "".join(parts)
        + "</svg></div>"
    )


# ---------------------------------------------------------------- Elo 趋势
def elo_trend_svg(series):
    """series: list of {date, elo: {id: value}}。返回内联 SVG 折线图。"""
    dates = [s["date"] for s in series]
    ids = sorted({k for s in series for k in s["elo"]})
    W, H = 380, 220
    pad_l, pad_r, pad_t, pad_b = 42, 12, 16, 30
    ymin = min(v for s in series for v in s["elo"].values()) - 10
    ymax = max(v for s in series for v in s["elo"].values()) + 10
    xw, yh = W - pad_l - pad_r, H - pad_t - pad_b

    def px(i):
        return pad_l + xw * (i / (len(dates) - 1 if len(dates) > 1 else 1))

    def py(v):
        return pad_t + yh * (1 - (v - ymin) / (ymax - ymin))

    parts = []
    for g in range(5):
        v = ymin + (ymax - ymin) * g / 4
        y = py(v)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{W - pad_r}" y2="{y:.1f}" stroke="#EEF0F6" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l - 6}" y="{y + 3:.1f}" font-size="10" fill="#9AA1B0" text-anchor="end">{v:.0f}</text>')
    for i, d in enumerate(dates):
        x = px(i)
        parts.append(f'<text x="{x:.1f}" y="{H - 8}" font-size="10" fill="#9AA1B0" text-anchor="middle">{d[5:]}</text>')
    for i, gid in enumerate(ids):
        color = COLORS.get(gid, "#8B5CF6")
        pts = " ".join(f"{px(j):.1f},{py(s['elo'][gid]):.1f}" for j, s in enumerate(series) if gid in s["elo"])
        if len(pts.split()) >= 2:
            parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"/>')
        for j, s in enumerate(series):
            if gid in s["elo"]:
                parts.append(f'<circle cx="{px(j):.1f}" cy="{py(s["elo"][gid]):.1f}" r="3" fill="{color}"/>')
    lg_x = W / 2 - (len(ids) * 92) / 2
    for i, gid in enumerate(ids):
        lx = lg_x + i * 92
        parts.append(f'<rect x="{lx:.0f}" y="2" width="10" height="10" rx="2" fill="{COLORS.get(gid, "#8B5CF6")}"/>')
        parts.append(f'<text x="{lx + 14:.0f}" y="11" font-size="10" fill="#2A2F3A">{esc(LABELS.get(gid, gid))}</text>')
    return (
        f'<div class="cv-chart"><svg viewBox="0 0 {W} {H}" role="img" aria-label="Elo 历史趋势">'
        + "".join(parts)
        + "</svg></div>"
    )


# ---------------------------------------------------------------- 正文
def build_sections(models, by_id, history, used_period="最近一期"):
    groups = []
    missing_dims = []
    for tid in TARGETS:
        m = by_id[tid]
        dims = m.get("dims") or {}
        absent = [label for key, label in DIMS if dims.get(key) is None]
        if absent:
            missing_dims.append(f"{LABELS[tid]}（{'、'.join(absent)}）")
        groups.append((tid, LABELS[tid], COLORS[tid], dims))
    if missing_dims:
        # 数据源换了测评口径时不要整篇崩掉：缺维度按「—」展示，雷达图按 0 处理
        print(f"[warn] 部分模型缺少维度数据：{'；'.join(missing_dims)}", file=sys.stderr)
    radar = radar_svg(groups)

    # 一、引言（按当前数据生成，避免换对比对象后叙事失真）
    dim_names = " / ".join(label for _, label in DIMS)
    intro_bits = []
    for tid in TARGETS:
        m = by_id[tid]
        intro_bits.append(
            f"<b>{LABELS[tid]}（{esc(m.get('provider',''))}）</b>"
            f"{'，开源' if m.get('open') else '，闭源'}"
            f"· Elo {m.get('elo') or '—'}"
        )
    sec_intro = (
        "<h2>一、为什么是这三个</h2>"
        f"<p>子维度评分（SuperCLUE {used_period} 新口径，覆盖 {dim_names}）"
        "公布分项分的头部模型中，" + "、".join(intro_bits) +
        " 三者最具代表性：分别是国产开源新旗舰、国际闭源榜首与国产高性价比路线。"
        "本文用同一套维度数据、同一套价格口径，把它们放在一起对比。</p>"
    )

    # 二、雷达图 + 拆解
    sec_radar = (
        "<h2>二、维度能力雷达图</h2>"
        f"<p>雷达图叠加三个模型在 {len(DIMS)} 个维度（{dim_names}）的得分，越靠外越强。"
        "一眼可见：三家形状差异明显，各有强项。</p>"
        + radar
    )

    # 六维逐项拆解表
    rows = []
    for dim, label in DIMS:
        vals = {tid: (by_id[tid].get("dims") or {}).get(dim) for tid in TARGETS}
        present = [v for v in vals.values() if v is not None]
        best = max(present) if present else None
        cells = ""
        for tid in TARGETS:
            v = vals[tid]
            if v is None:
                cells += "<td>—</td>"
                continue
            is_best = best is not None and v == best
            mark = ' class="cv-best"' if is_best else ""
            cells += f"<td{mark}><b>{v:.1f}</b>{' ★' if is_best else ''}</td>"
        rows.append(f"<tr><td>{label}</td>{cells}</tr>")
    # 逐维度冠军（数据驱动，避免换对比对象后叙事失真）
    dim_winners = []
    for dim, label in DIMS:
        best_tid, best_v = None, None
        for tid in TARGETS:
            v = (by_id[tid].get("dims") or {}).get(dim)
            if v is not None and (best_v is None or v > best_v):
                best_tid, best_v = tid, v
        if best_tid:
            dim_winners.append((label, best_tid, best_v))

    insight_bits = []
    for i, (label, tid, v) in enumerate(dim_winners[:3], 1):
        insight_bits.append(
            f"{'①②③'[i-1]} <b>{LABELS[tid]} 的{label} {v:.1f} 为三者最高</b>；")
    # 三家共同低分维度 = 按三家最高值排序后最低的维度
    dim_maxes = []
    for key, label in DIMS:
        vals = [(by_id[tid].get("dims") or {}).get(key) for tid in TARGETS]
        present = [v for v in vals if v is not None]
        if present:
            dim_maxes.append((key, label, max(present)))
    if dim_maxes:
        low_key, low_label, low_max = min(dim_maxes, key=lambda x: x[2])
        insight_bits.append(
            f"相对而言，<b>{low_label}</b> 是三家共同的低分维度（三者最高仅 {low_max:.1f}），"
            "选型时若强依赖该能力，建议用业务数据实测后再定。")
    sec_table = (
        "<h3>逐维度拆解</h3>"
        "<table><thead><tr><th>维度</th>"
        + "".join(f"<th>{LABELS[t]}</th>" for t in TARGETS)
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        "<p><b>读法</b>：★ 为该维度最高分。" + "".join(insight_bits) + "</p>"
    )

    # 三、Elo 与趋势
    snaps = history.get("snapshots", [])
    series = []
    for s in snaps:
        elo = {tid: m["elo"] for tid in TARGETS for m in s["models"] if m["id"] == tid}
        if elo:
            series.append({"date": s["date"], "elo": elo})
    cur_rows = "".join(
        f"<tr><td>{LABELS[t]}</td><td><b>{by_id[t].get('elo') if by_id[t].get('elo') is not None else '—'}</b></td>"
        f"<td>{'开源' if by_id[t].get('open') else '闭源'}</td>"
        f"<td>{(by_id[t].get('context') or 0) // 1000}k</td>"
        f"<td>{fmt_val(by_id[t].get('superclue'), 1)}</td></tr>"
        for t in TARGETS
    )
    # 近期走势（数据驱动：取每家最近两个快照点比较）
    trend_bits = []
    for tid in TARGETS:
        pts = [(s["date"], s["elo"][tid]) for s in series if tid in s["elo"]]
        if len(pts) >= 2:
            d0, d1 = pts[-2], pts[-1]
            delta = d1[1] - d0[1]
            trend_bits.append(
                f"{LABELS[tid]} 从 {d0[1]}（{d0[0]}）到 {d1[1]}（{d1[0]}，{'%+d' % delta}）")
    trend_text = ("近两期快照走势：" + "；".join(trend_bits) + "。"
                  if trend_bits else "（历史快照积累中，趋势解读稍后自动补充。）")
    sec_elo = (
        "<h2>三、Elo 综合排名与历史趋势</h2>"
        "<p>Elo 来自 LMArena 竞技场，反映真实用户盲测的胜率偏好，是「综合体验」的参考指标。</p>"
        "<table><thead><tr><th>模型</th><th>当前 Elo</th><th>开源</th><th>上下文</th><th>SuperCLUE</th></tr></thead>"
        f"<tbody>{cur_rows}</tbody></table>"
        + (elo_trend_svg(series) if len(series) >= 2 else "<p>（历史快照不足，趋势图暂缺）</p>")
        + f"<p>{trend_text}排名波动主要来自新模型入榜与评测样本更新。</p>"
    )

    # 四、价格与性价比
    def ratio(tid):
        m = by_id[tid]
        if m.get("priceIn") and m["priceIn"] > 0 and m.get("elo"):
            return m["elo"] / cny_val(m, m["priceIn"])
        return None

    pr_rows = "".join(
        f"<tr><td>{LABELS[t]}</td><td>{fmt_cny(by_id[t], 'priceIn')}</td>"
        f"<td>{fmt_cny(by_id[t], 'priceOut')}</td><td>{fmt_val(ratio(t), 0)}</td></tr>"
        for t in TARGETS
    )
    # 价格与性价比（数据驱动）
    priced = [(t, ratio(t)) for t in TARGETS if ratio(t) is not None]
    price_para = ""
    if priced:
        best_t, best_r = max(priced, key=lambda x: x[1])
        price_para = (
            f"<p><b>{LABELS[best_t]}</b> 的性价比指数最高（Elo ÷ 输入价 ≈ {best_r:.0f}），"
            "对成本敏感的大规模调用可优先考虑；其余两家适合对能力上限要求更高的场景。"
            "价格缺失的模型表示暂无公开报价，不计入性价比排序。</p>"
        )
    sec_price = (
        "<h2>四、价格与性价比</h2>"
        "<p>价格为公开 API 报价（每百万 tokens：国产模型为官方人民币报价，海外按 $1≈¥7.2 换算）；性价比 = Elo ÷ 输入价（折算为 ¥）。</p>"
        "<table><thead><tr><th>模型</th><th>输入价</th><th>输出价</th><th>性价比指数</th></tr></thead>"
        f"<tbody>{pr_rows}</tbody></table>"
        + price_para
    )

    # 五、结论
    # 五、结论（按各维度冠军生成场景建议）
    def winner_of(key):
        cand = [(by_id[t].get("dims") or {}).get(key, -1) for t in TARGETS]
        return TARGETS[max(range(len(cand)), key=lambda i: cand[i])]

    best_coding = winner_of("coding")
    best_math = winner_of("math")
    best_hallu = winner_of("hallu")
    best_price = priced[0][0] if priced else None
    best_elo = max(TARGETS, key=lambda t: by_id[t].get("elo") or 0)

    def li(scenario, tid, reason):
        m = by_id[tid]
        extra = ""
        if reason == "elo":
            extra = f"Elo {m.get('elo')} 三家最高"
        else:
            v = (m.get("dims") or {}).get(reason)
            label = dict(DIMS).get(reason, reason)
            extra = f"{label} {v:.1f} 领先" if v is not None else "该维度领先"
        return f"<li><b>{scenario}</b>：优先看 <b>{LABELS[tid]}</b>（{extra}）。</li>"

    price_li = ""
    if best_price:
        m = by_id[best_price]
        price_li = (f"<li><b>成本敏感 / 大规模调用</b>：<b>{LABELS[best_price]}</b>"
                    f"（输入 {fmt_cny(m, 'priceIn')}，性价比指数最高）。</li>")
    sec_close = (
        "<h2>五、结论：什么场景选谁</h2>"
        "<ul>"
        + li("要综合体验上限", best_elo, "elo")
        + li("要写代码 / 智能体编程", best_coding, "coding")
        + li("要数理与推理能力", best_math, "math")
        + li("要事实可靠性（低幻觉）", best_hallu, "hallu")
        + price_li
        + "<li><b>强约束输出</b>：无论选哪家，结构化输出都建议在应用层加 Schema 校验。</li>"
        "</ul>"
        "<blockquote>数据口径：子维度评分来自 SuperCLUE "
        + esc(used_period) + " 口径测评（2026-11 起为新口径，与此前各期不可直接对比）；"
        "Elo 来自 LMArena；价格为公开 API 报价。完整榜单见<a href=\"../rank.html\">排行榜</a>，"
        "更多对比可用<a href=\"../compare.html\">模型对比工具</a>。</blockquote>"
    )

    return [sec_intro, sec_radar, sec_table, sec_elo, sec_price, sec_close]


NAV = """<header class="nav">
  <div class="nav-inner">
    <a class="brand" href="../index.html"><svg class="brand-mark" viewBox="0 0 64 64" width="22" height="22" aria-hidden="true" focusable="false"><rect width="64" height="64" rx="16" fill="#1E1B4B"/><text x="19.5" y="44.5" font-size="34" fill="#FFFFFF" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif">M</text><rect x="33" y="39" width="4.5" height="11.5" rx="2.2" fill="#8B5CF6"/><rect x="40" y="32" width="4.5" height="18.5" rx="2.2" fill="#8B5CF6"/><rect x="47" y="25" width="4.5" height="25.5" rx="2.2" fill="#8B5CF6"/></svg>MaaS Rank</a>
    <button class="nav-toggle" aria-label="打开导航" aria-expanded="false">☰</button>
    <nav>
      <a href="../index.html">首页</a>
      <a href="../rank.html">排行榜</a>
      <a href="../compare.html">模型对比</a>
      <a href="../report.html">榜单周报</a>
      <a href="../articles.html" class="active">榜单解读</a>
      <a href="../about.html">数据说明</a>
    </nav>
    <div class="nav-extra">
      <a href="https://github.com/maas-cjy/maas-rank" target="_blank" rel="noopener">GitHub</a>
    </div>
  </div>
</header>"""

BAIDU_STAT = """<!-- 百度统计 -->
<script>
var _hmt = _hmt || [];
(function() {
  var hm = document.createElement("script");
  hm.src = "https://hm.baidu.com/hm.js?d3e2eb9c2ec97fd57da3493e0b6788f3";
  var s = document.getElementsByTagName("script")[0];
  s.parentNode.insertBefore(hm, s);
})();
</script>"""


def build_page(date, title, summary, tags, body_html, fname, category="模型对比"):
    tag_meta = "".join(f'<meta name="article:tag" content="{esc(t)}">' for t in tags)
    tag_html = "".join(f'<span class="art-tag">{esc(t)}</span>' for t in tags)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{esc(summary)}">
<meta name="keywords" content="模型对比,大模型实测,Qwen,Kimi,DeepSeek,六维评测,{esc(','.join(tags))}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{BASE}articles/{fname}">
<meta name="theme-color" content="#1E1B4B">
<link rel="icon" type="image/svg+xml" href="../assets/logo.svg">
<title>{esc(title)} | MaaS Rank 大模型排行榜</title>
<meta property="og:type" content="article">
<meta property="og:site_name" content="MaaS Rank">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(summary)}">
<meta property="og:image" content="{BASE}assets/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="{BASE}articles/{fname}">
<meta property="og:locale" content="zh_CN">
<meta property="article:published_time" content="{date}">
{tag_meta}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(summary)}">
<meta name="twitter:image" content="{BASE}assets/og-image.png">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Article","headline":{json.dumps(title, ensure_ascii=False)},"datePublished":"{date}","dateModified":"{date}","url":"{BASE}articles/{fname}","publisher":{{"@type":"Organization","name":"MaaS Rank"}},"inLanguage":"zh-CN"}}
</script>
<link rel="stylesheet" href="../css/style.css">
</head>
<body>

{NAV}

<main>
  <div class="article-wrap">
    <div class="article-head">
      <h1>{esc(title)}</h1>
      <div class="article-meta">
        <span>{date}</span><span>·</span><span>{esc(category)}</span><span>·</span>
        <span>MaaS Rank</span>
        <span class="art-tags">{tag_html}</span>
      </div>
      <div class="update-banner">本周已更新 · 数据截至 {date}</div>
    </div>
    <article class="article-body">
{body_html}
    </article>
    <div class="article-foot">
      <a class="act-btn" href="../rank.html">查看完整榜单 →</a>
      <a class="act-btn" href="../compare.html">自己动手对比 →</a>
      <a class="act-btn" href="../articles.html">更多解读 →</a>
    </div>
  </div>
</main>

<footer>
  <div>MaaS Rank · 大模型排行榜 · 本页更新于 {date} · 数据口径见<a href="../about.html">数据说明</a></div>
</footer>

<script src="../js/site.js"></script>
{BAIDU_STAT}
<script src="../js/analytics.js"></script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", action="store_true", help="生成草稿（不进 sitemap 与列表）")
    args = ap.parse_args()

    data = load("data/models.json", {})
    models = data.get("models", [])
    by_id = {m["id"]: m for m in models}
    missing = [t for t in TARGETS if t not in by_id]
    if missing:
        print(f"[error] 缺少对比模型: {missing}", file=sys.stderr)
        return 1
    for t in TARGETS:
        if not by_id[t].get("dims"):
            print(f"[error] {t} 无子维度评分 dims", file=sys.stderr)
            return 1

    history = load("data/history.json", {})
    meta = data.get("meta", {})
    date = meta.get("updated", "2026-09")
    used_period = ((meta.get("fieldInfo") or {}).get("superclue") or {}).get("date", "最近一期")
    month = date[:7]
    fname = f"compare-{month}.html"
    names = " vs ".join(LABELS[t] for t in TARGETS)
    title = f"{month} 旗舰模型实测：{names} 五维对比"
    summary = (f"基于 SuperCLUE {used_period} 口径的子维度评分与 LMArena Elo，对 {names} 做"
               f"维度雷达、Elo 趋势、价格与性价比的横向对比，给出分场景选型结论，随数据自动更新。")
    tags = ["模型对比", "维度评测", "大模型选型"]

    body_html = "\n".join(build_sections(models, by_id, history, used_period))

    articles = load("data/articles.json", [])
    os.makedirs(os.path.join(ROOT, "articles"), exist_ok=True)
    with open(os.path.join(ROOT, "articles", fname), "w", encoding="utf-8") as f:
        f.write(build_page(date, title, summary, tags, body_html, fname))

    entry = {
        "file": fname, "title": title, "date": date, "issue": None,
        "summary": summary, "tags": tags,
    }
    if args.draft:
        entry["draft"] = True
    articles = [a for a in articles if a.get("file") != fname]
    articles.insert(0, entry)
    with open(os.path.join(ROOT, "data", "articles.json"), "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[ok] 已生成 articles/{fname}{'（草稿）' if args.draft else ''}")
    print(f"     标题：{title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
