#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每周榜单解读文章生成器。

基于 data/models.json（当期）、data/prev.json（上期）、data/history.json（历史快照）
生成一篇原创解读文章（articles/<日期>-weekly.html），并登记进 data/articles.json。

用法：
    python scripts/gen_weekly_article.py           # 生成并发布
    python scripts/gen_weekly_article.py --draft   # 生成草稿（不进 sitemap，列表页不显示）

生成后建议人工润色文章正文（直接编辑 HTML 文件），补充观点与结论。
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD_BASE = "https://maas-cjy.github.io/maas-rank/"

DIM_LABELS = [
    ("math", "数学推理"), ("hallu", "幻觉控制"), ("science", "科学推理"),
    ("ifollow", "精确指令遵循"), ("coding", "智能体编程"), ("plan", "智能体任务规划"),
]


def esc(s):
    return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def load(path, default):
    p = os.path.join(ROOT, path)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def fmt_cny(v):
    if v is None:
        return "—"
    return f"¥{v * 7.2:.1f}" if v >= 1 else f"¥{v * 7.2:.2f}"


def fmt_price(v):
    return "—" if v is None else f"${v:g}"


def top_n(seq, key, n=5, reverse=True):
    return sorted([m for m in seq if m.get(key) is not None], key=lambda x: x[key], reverse=reverse)[:n]


def analyze(models, prev, hist):
    """从数据中提炼文章要点。"""
    prev_models = (prev or {}).get("models", [])
    prev_by_id = {m["id"]: m for m in prev_models}
    prev_date = (prev or {}).get("date", "上期")

    elo_top = top_n(models, "elo", 10)
    sc_top = top_n(models, "superclue", 5)
    bench_top = top_n(models, "bench", 3)
    cheap_top = top_n(models, "priceIn", 5, reverse=False)
    ctx_top = top_n(models, "context", 5)

    # Elo 变化
    ups, downs, news, outs, price_changes = [], [], [], [], []
    for m in models:
        pm = prev_by_id.get(m["id"])
        if not pm:
            news.append(m)
            continue
        if m.get("elo") is not None and pm.get("elo") is not None:
            d = m["elo"] - pm["elo"]
            if d > 0:
                ups.append((m, d))
            elif d < 0:
                downs.append((m, d))
        for pk, label in (("priceIn", "输入"), ("priceOut", "输出")):
            if m.get(pk) is not None and pm.get(pk) is not None and m[pk] != pm[pk]:
                price_changes.append((m, label, pm[pk], m[pk]))
    outs = [pm for mid, pm in prev_by_id.items() if mid not in {m["id"] for m in models}]

    # 历史趋势（Elo 前 3 名模型）
    snaps = (hist or {}).get("snapshots", [])
    trend = []
    for m in elo_top[:3]:
        pts = []
        for s in snaps:
            sm = next((x for x in s.get("models", []) if x.get("id") == m["id"]), None)
            if sm and sm.get("elo") is not None:
                pts.append((s.get("date", ""), sm["elo"]))
        if m.get("elo") is not None:
            pts.append(("本期", m["elo"]))
        if len(pts) >= 2:
            trend.append((m, pts))

    return {
        "prev_date": prev_date, "elo_top": elo_top, "sc_top": sc_top, "bench_top": bench_top,
        "cheap_top": cheap_top, "ctx_top": ctx_top, "ups": ups, "downs": downs,
        "news": news, "outs": outs, "price_changes": price_changes, "trend": trend,
        "total": len(models),
    }


def build_sections(d, date):
    """生成文章正文 HTML 各节。"""
    models_total = d["total"]
    e1 = d["elo_top"][0] if d["elo_top"] else None
    s1 = d["sc_top"][0] if d["sc_top"] else None
    b1 = d["bench_top"][0] if d["bench_top"] else None
    c1 = d["cheap_top"][0] if d["cheap_top"] else None
    has_change = bool(d["ups"] or d["downs"] or d["news"] or d["price_changes"])

    # ---------- 导语 ----------
    lead = [f"本期（{date}）榜单共收录 <b>{models_total}</b> 个模型"]
    if e1:
        lead.append(f"竞技场方面，<b>{esc(e1['name'])}</b>（{esc(e1.get('provider',''))}）以 <b>{e1['elo']}</b> 的 Elo 分继续领跑" if not has_change
                    else f"竞技场方面，<b>{esc(e1['name'])}</b>（{esc(e1.get('provider',''))}）以 <b>{e1['elo']}</b> 的 Elo 分占据榜首")
    if s1:
        lead.append(f"中文能力上，<b>{esc(s1['name'])}</b> 的 SuperCLUE 智能指数为 <b>{s1['superclue']:.1f}</b>")
    if b1:
        lead.append(f"综合能力分（SuperCLUE 六维均值）第一为 <b>{esc(b1['name'])}</b>（{b1['bench']:.2f} 分）")
    if c1:
        lead.append(f"最便宜的模型是 <b>{esc(c1['name'])}</b>，输入价格 {fmt_cny(c1['priceIn'])} / 百万 tokens")
    lead_html = "<p>" + "；".join(lead) + "。</p>"

    # ---------- 一、榜单总览 ----------
    fixed_rows = []
    for i, m in enumerate(d["elo_top"], 1):
        bench = f"{m['bench']:.1f}" if m.get("bench") is not None else "—"
        sc = f"{m['superclue']:.1f}" if m.get("superclue") is not None else "—"
        fixed_rows.append(
            f"<tr><td>{i}</td>"
            f"<td><a href=\"../model.html?id={esc(m['id'])}\">{esc(m['name'])}</a></td>"
            f"<td>{esc(m.get('provider',''))}</td><td>{m.get('elo','—')}</td>"
            f"<td>{sc}</td><td>{bench}</td></tr>"
        )
    sec_overview = (
        "<h2>一、榜单总览</h2>"
        "<p>先看竞技场 Elo Top 10（点击模型名可进入详情页查看六维能力与历史趋势）：</p>"
        "<table><thead><tr><th>排名</th><th>模型</th><th>厂商</th><th>Elo</th><th>SuperCLUE</th><th>综合能力</th></tr></thead>"
        f"<tbody>{''.join(fixed_rows)}</tbody></table>"
    )

    # ---------- 二、本周变化 ----------
    if has_change:
        parts = ["<h2>二、本周变化</h2>"]
        if d["ups"]:
            ups_sorted = sorted(d["ups"], key=lambda x: -x[1])[:5]
            lis = "".join(f"<li><a href=\"../model.html?id={esc(m['id'])}\">{esc(m['name'])}</a>：{pm['elo']} → {m['elo']}（<b>+{delta}</b>）</li>"
                          for m, delta in ups_sorted)
            parts.append(f"<h3>涨幅居前</h3><ul>{lis}</ul>")
        if d["downs"]:
            downs_sorted = sorted(d["downs"], key=lambda x: x[1])[:5]
            lis = "".join(f"<li><a href=\"../model.html?id={esc(m['id'])}\">{esc(m['name'])}</a>：{pm['elo']} → {m['elo']}（{delta}）</li>"
                          for m, delta in downs_sorted)
            parts.append(f"<h3>回落明显</h3><ul>{lis}</ul>")
        if d["news"]:
            lis = "".join(f"<li><a href=\"../model.html?id={esc(m['id'])}\">{esc(m['name'])}</a>（{esc(m.get('provider',''))}，Elo {m.get('elo','—')}）</li>"
                          for m in d["news"][:8])
            more = " …" if len(d["news"]) > 8 else ""
            parts.append(f"<h3>新上榜</h3><ul>{lis}{more}</ul>")
        if d["outs"]:
            lis = "".join(f"<li>{esc(m.get('name',''))}（上期 Elo {m.get('elo','—')}）</li>" for m in d["outs"][:8])
            more = " …" if len(d["outs"]) > 8 else ""
            parts.append(f"<h3>退出榜单</h3><ul>{lis}{more}</ul>")
        if d["price_changes"]:
            lis = "".join(f"<li><a href=\"../model.html?id={esc(m['id'])}\">{esc(m['name'])}</a> {label}价：{fmt_price(old)} → <b>{fmt_price(new)}</b></li>"
                          for m, label, old, new in d["price_changes"][:8])
            parts.append(f"<h3>价格调整</h3><ul>{lis}</ul>")
        sec_change = "".join(parts)
    else:
        sec_change = (
            f"<h2>二、本周变化：榜单进入稳定期</h2>"
            f"<p>与上一期（{d['prev_date']}）快照相比，本期榜单的 Elo 排名、SuperCLUE 得分与 API 价格均未发生变化。"
            "这通常意味着两件事：其一，LMArena 官方未发布新的 Elo 快照（竞技场数据为不定期更新）；"
            "其二，各厂商处于发版间歇期，没有新模型入榜或调价。</p>"
            "<p>稳定期恰恰是做「横评」的好窗口——排名不再频繁跳动，同一套数据下的模型对比结论更耐得住推敲。"
            "推荐使用<a href=\"../compare.html\">模型对比</a>工具，把关注的两三个模型拉到同一张雷达图下看六维差异。</p>"
        )

    # ---------- 三、综合能力看点 ----------
    if d["bench_top"]:
        parts = ["<h2>三、综合能力看点：六维数据说明了什么</h2>",
                 "<p>综合能力分取 SuperCLUE 六个维度的平均分，本期前三名：</p>"]
        for m in d["bench_top"]:
            dims = m.get("dims") or {}
            dim_html = "".join(f"<td>{lbl}<br><b>{dims.get(k, '—')}</b></td>" for k, lbl in DIM_LABELS)
            parts.append(
                f"<p style=\"margin-bottom:6px;\"><b><a href=\"../model.html?id={esc(m['id'])}\">{esc(m['name'])}</a></b>（{esc(m.get('provider',''))}）—— {m['bench']:.2f} 分</p>"
                f"<table><tbody><tr>{dim_html}</tr></tbody></table>"
            )
        parts.append(
            "<p>几点观察：</p><ul>"
            "<li><b>头部差距很小</b>：前三名分差在 2 分以内，选型时不必迷信「第一名」，维度强弱比总分更值得关注；</li>"
            "<li><b>维度差异才是选型依据</b>：重数学/科学推理的场景看推理维度，做 Agent 应用重点看智能体编程与任务规划两项；</li>"
            "<li><b>注意口径</b>：海外模型若未参加当期 SuperCLUE 测评，榜单展示为参考估算值，横向对比时请留意标注。</li>"
            "</ul>"
        )
        sec_bench = "".join(parts)
    else:
        sec_bench = ""

    # ---------- 四、价格动向 ----------
    parts = ["<h2>四、价格动向：谁的性价比更高</h2>"]
    if d["cheap_top"]:
        rows = "".join(
            f"<tr><td><a href=\"../model.html?id={esc(m['id'])}\">{esc(m['name'])}</a></td>"
            f"<td>{esc(m.get('provider',''))}</td>"
            f"<td>{fmt_cny(m['priceIn'])} / {fmt_cny(m['priceOut'])}</td>"
            f"<td>{'开源' if m.get('open') else '闭源'}</td></tr>"
            for m in d["cheap_top"]
        )
        parts.append(
            "<p>当前输入价格最低的五个模型（输入 / 输出，每百万 tokens，按 1 美元 ≈ 7.2 元换算）：</p>"
            "<table><thead><tr><th>模型</th><th>厂商</th><th>输入 / 输出价</th><th>开源</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    if d["price_changes"]:
        parts.append("<p>本周有价格调整，详见上文变化部分。</p>")
    else:
        parts.append("<p>本周各厂商定价无变化。整体来看，头部模型的价格战已阶段性趋缓，"
                     "「降价换量」的窗口期在收窄，按当前价格做年度成本测算风险不大。</p>")
    sec_price = "".join(parts)

    # ---------- 五、趋势 ----------
    if d["trend"]:
        parts = ["<h2>五、历史趋势：头部模型 Elo 走势</h2>"]
        for m, pts in d["trend"]:
            seq = " → ".join(f"{dt}（{v}）" for dt, v in pts)
            delta = pts[-1][1] - pts[0][1]
            sign = "+" if delta >= 0 else ""
            parts.append(f"<p><b>{esc(m['name'])}</b>：{seq}（累计 <b>{sign}{delta}</b>）</p>")
        parts.append(
            "<p>从近几期走势看，头部位置的争夺集中在个位数 Elo 差距内，"
            "单周波动更多来自投票样本量的变化而非能力跃迁——看待周度排名变化时，"
            "建议以「趋势方向」而非「具体名次」为准。</p>"
        )
        sec_trend = "".join(parts)
    else:
        sec_trend = ""

    # ---------- 六、选型建议 ----------
    sec_advice = (
        "<h2>" + ("六" if sec_trend else "五") + "、选型建议</h2>"
        "<ul>"
        "<li><b>追求能力上限</b>：优先看竞技场 Elo Top 5，这些模型在真实人类盲测偏好中胜率最高；</li>"
        "<li><b>中文场景优先</b>：SuperCLUE 与综合能力分权重更高的国产头部模型，通常在中文理解与指令遵循上更稳；</li>"
        "<li><b>成本敏感型应用</b>：从低价模型里挑 Elo 高于中位数的，单位智能的成本能低一个数量级；</li>"
        "<li><b>长文档 / Agent 场景</b>：先筛上下文长度与智能体维度得分，再看价格。</li>"
        "</ul>"
        "<blockquote>以上结论基于公开榜单数据，仅供选型参考；正式决策前建议用自己的业务数据做小规模实测。</blockquote>"
    )

    return lead_html, [s for s in [sec_overview, sec_change, sec_bench, sec_price, sec_trend, sec_advice] if s]


def build_title_summary(d, date):
    e1 = d["elo_top"][0] if d["elo_top"] else None
    has_change = bool(d["ups"] or d["downs"] or d["news"] or d["price_changes"])
    if has_change and d["ups"]:
        m, delta = sorted(d["ups"], key=lambda x: -x[1])[0]
        title = f"{date} 榜单解读：{m['name']} 领涨 {delta} 分"
        if e1 and e1["id"] != m["id"]:
            title += f"，{e1['name']}稳居榜首"
    elif e1:
        title = f"{date} 榜单解读：{e1['name']} 继续 Elo 领跑，头部竞争胶着"
    else:
        title = f"{date} 大模型榜单解读"
    summary = (f"第 {{issue}} 期：本期收录 {d['total']} 个模型，"
               + (f"竞技场第一 {e1['name']}（{e1['elo']}），" if e1 else "")
               + ("榜单与上期一致，进入稳定期，" if not has_change else "本周榜单有新变化，")
               + "附 Top 10 总览、六维能力看点、价格动向与选型建议。")
    return title, summary


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


def build_page(date, issue, title, summary, tags, body_html):
    tag_meta = "".join(f'<meta name="article:tag" content="{esc(t)}">' for t in tags)
    tag_html = "".join(f'<span class="art-tag">{esc(t)}</span>' for t in tags)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{esc(summary)}">
<meta name="keywords" content="大模型排行榜,榜单解读,大模型评测,模型选型,{esc(','.join(tags))}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{OLD_BASE}articles/weekly-{date}.html">
<meta name="theme-color" content="#1E1B4B">
<link rel="icon" type="image/svg+xml" href="../assets/logo.svg">
<title>{esc(title)} | MaaS Rank 大模型排行榜</title>
<meta property="og:type" content="article">
<meta property="og:site_name" content="MaaS Rank">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(summary)}">
<meta property="og:image" content="{OLD_BASE}assets/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="{OLD_BASE}articles/weekly-{date}.html">
<meta property="og:locale" content="zh_CN">
<meta property="article:published_time" content="{date}">
{tag_meta}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(summary)}">
<meta name="twitter:image" content="{OLD_BASE}assets/og-image.png">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"BlogPosting","headline":{json.dumps(title, ensure_ascii=False)},"datePublished":"{date}","url":"{OLD_BASE}articles/weekly-{date}.html","publisher":{{"@type":"Organization","name":"MaaS Rank"}},"inLanguage":"zh-CN"}}
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
        <span>{date}</span><span>·</span><span>第 {issue} 期</span><span>·</span>
        <span>MaaS Rank</span>
        <span class="art-tags">{tag_html}</span>
      </div>
    </div>
    <article class="article-body">
{body_html}
    </article>
    <div class="article-foot">
      <a class="act-btn" href="../rank.html">查看完整榜单 →</a>
      <a class="act-btn" href="../report.html">榜单变化周报 →</a>
      <a class="act-btn" href="../articles.html">更多解读 →</a>
    </div>
  </div>
</main>

<footer>
  <div>MaaS Rank · 大模型排行榜 · 本页发布于 {date} · 数据口径见<a href="../about.html">数据说明</a></div>
</footer>

<script src="../js/site.js"></script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", action="store_true", help="生成草稿（不进 sitemap 与列表）")
    args = ap.parse_args()

    data = load("data/models.json", {})
    models = data.get("models", [])
    if not models:
        print("[error] data/models.json 无数据，请先运行 fetch_data.py", file=sys.stderr)
        return 1
    date = data.get("meta", {}).get("updated")

    prev = load("data/prev.json", {})
    hist = load("data/history.json", {})

    d = analyze(models, prev, hist)
    articles = load("data/articles.json", [])
    fname = f"weekly-{date}.html"
    issue = len([a for a in articles if "weekly" in a.get("file", "") and a.get("file") != fname]) + 1

    title, summary = build_title_summary(d, date)
    summary = summary.replace("{issue}", str(issue))
    tags = ["周榜解读", "Elo", "选型建议"]

    lead, sections = build_sections(d, date)
    body_html = lead + "\n".join(sections)

    os.makedirs(os.path.join(ROOT, "articles"), exist_ok=True)
    with open(os.path.join(ROOT, "articles", fname), "w", encoding="utf-8") as f:
        f.write(build_page(date, issue, title, summary, tags, body_html))

    entry = {
        "file": fname, "title": title, "date": date, "issue": issue,
        "summary": summary, "tags": tags,
    }
    if args.draft:
        entry["draft"] = True
    articles = [a for a in articles if a.get("file") != fname]
    articles.insert(0, entry)  # 最新的在前
    with open(os.path.join(ROOT, "data", "articles.json"), "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[ok] 已生成 articles/{fname}（第 {issue} 期{'，草稿' if args.draft else ''}）")
    print(f"     标题：{title}")
    print(f"     摘要：{summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
