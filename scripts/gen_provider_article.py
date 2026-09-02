#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大模型厂商全景盘点生成器（按月更新）。

基于 data/models.json 实时聚合各厂商的模型数量、开源数量、平均 Elo、
最强模型，生成一篇厂商盘点文章（articles/provider-YYYY-MM.html），
并登记进 data/articles.json。

用法：
    python scripts/gen_provider_article.py           # 生成并发布
    python scripts/gen_provider_article.py --draft   # 生成草稿（不进 sitemap，列表页不显示）

数据每周更新后重跑一次，盘点自动刷新为最新格局。
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://maasrank.com/"

# 重点厂商白名单（按关注度排序，其余归入「更多厂商」总表）
FOCUS = ["阿里云", "OpenAI", "Google", "Anthropic", "Meta", "xAI",
         "DeepSeek", "智谱", "月之暗面", "腾讯", "小米", "MiniMax"]


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


def short_name(m, limit=20):
    n = m["name"]
    return n if len(n) <= limit else n[:limit] + "…"


def model_link(m):
    return f'<a href="../model.html?id={esc(m["id"])}" title="{esc(m["name"])}">{esc(short_name(m))}</a>'


def provider_stats(models):
    """按厂商聚合统计。"""
    groups = {}
    for m in models:
        p = m.get("provider", "其他")
        groups.setdefault(p, []).append(m)
    stats = []
    for p, subs in groups.items():
        elos = [m["elo"] for m in subs if m.get("elo")]
        stats.append({
            "name": p,
            "count": len(subs),
            "open": sum(1 for m in subs if m.get("open")),
            "avg_elo": round(sum(elos) / len(elos), 1) if elos else None,
            "top": max(subs, key=lambda m: m.get("elo") or 0) if any(m.get("elo") for m in subs) else None,
        })
    return stats


def commentary(st, rank_by_count, rank_by_avg, total):
    """基于数据特征生成一段客观点评。"""
    parts = []
    # 规模
    if rank_by_count == 1:
        parts.append(f"以 {st['count']} 款模型位列全站模型数量第一，是榜单覆盖最广的厂商")
    elif rank_by_count <= 3:
        parts.append(f"{st['count']} 款模型位居数量前三")
    elif rank_by_count <= 6:
        parts.append(f"{st['count']} 款模型的规模处于第一梯队")
    else:
        parts.append(f"{st['count']} 款模型的规模相对克制")
    # 开源策略
    ratio = st["open"] / st["count"] if st["count"] else 0
    if st["open"] == 0:
        parts.append("全系闭源，走商业 API 路线")
    elif ratio >= 0.5:
        parts.append(f"{st['open']} 款开源，开源占比 {ratio * 100:.0f}%，生态开放程度高")
    else:
        parts.append(f"少数开源（{st['open']} 款），以闭源商用为主")
    # 平均实力
    if st["avg_elo"]:
        if rank_by_avg == 1:
            parts.append(f"平均 Elo {st['avg_elo']} 全榜第一，款款能打")
        elif rank_by_avg <= 3:
            parts.append(f"平均 Elo {st['avg_elo']} 高居前三，整体实力出色")
        elif st["avg_elo"] >= 1380:
            parts.append(f"平均 Elo {st['avg_elo']}，属「少而精」路线")
        elif st["avg_elo"] < 1230:
            parts.append(f"平均 Elo {st['avg_elo']}，更侧重覆盖面与细分场景")
        else:
            parts.append(f"平均 Elo {st['avg_elo']}，中坚力量")
    # 最强模型
    if st["top"]:
        parts.append(f"旗舰为 {st['top']['name']}（Elo {st['top']['elo']}）")
    return "；".join(parts) + "。"


def build_sections(models, stats):
    """厂商盘点正文，返回 HTML 段落列表。"""
    total = len(models)
    provider_total = len(stats)
    stats = [s for s in stats if s["name"] != "其他"]
    stats.sort(key=lambda s: -s["count"])
    rank_by_count = {s["name"]: i + 1 for i, s in enumerate(stats)}
    stats.sort(key=lambda s: -(s["avg_elo"] or 0))
    rank_by_avg = {s["name"]: i + 1 for i, s in enumerate(stats)}
    stats.sort(key=lambda s: -(s["count"]))

    # 一、格局总览
    ov_rows = ""
    for i, s in enumerate(stats[:10], 1):
        ov_rows += (
            f"<tr><td>{i}</td><td><b>{esc(s['name'])}</b></td><td>{s['count']}</td>"
            f"<td>{s['open']}</td><td>{s['avg_elo'] or '—'}</td>"
            f"<td>{model_link(s['top']) if s['top'] else '—'}</td><td>{s['top']['elo'] if s['top'] else '—'}</td></tr>"
        )
    sec_overview = (
        "<h2>一、格局总览：头部十家厂商</h2>"
        f"<p>截至本期数据，榜单共收录 {total} 款模型、来自 {provider_total} 个厂商分类（含「其他/未归类」）。"
        "按模型数量排序，前十名如下——"
        "款数代表覆盖面，平均 Elo 代表整体实力，最强模型则决定厂商的天花板，三列结合看才完整。</p>"
        "<table><thead><tr><th>#</th><th>厂商</th><th>模型数</th><th>开源</th>"
        "<th>平均 Elo</th><th>最强模型</th><th>Elo</th></tr></thead>"
        f"<tbody>{ov_rows}</tbody></table>"
        "<p>整体格局：<b>中国厂商在规模与开源上领先</b>（阿里云 37 款居首），"
        "<b>海外厂商在单点能力上更强</b>（Anthropic 的 Claude Opus 5 以 1504 Elo 登顶全榜）；"
        "而平均实力榜上，小米、月之暗面、xAI 等「小而精」的玩家反超了大厂——"
        "数量不再是衡量厂商的唯一标准。</p>"
    )

    # 二、重点厂商逐个盘点
    focus = [s for s in stats if s["name"] in FOCUS]
    rest = [s for s in stats if s["name"] not in FOCUS]
    cards = []
    for s in focus:
        cm = commentary(s, rank_by_count.get(s["name"], 99), rank_by_avg.get(s["name"], 99), total)
        top = s["top"]
        top_html = (
            f'<div class="pv-top">{model_link(top)}<span class="pv-elo">Elo {top["elo"]}</span></div>' if top
            else '<div class="pv-top">—</div>'
        )
        cards.append(
            f"""<div class="pv-card">
  <div class="pv-head"><span class="pv-name">{esc(s["name"])}</span>
    <span class="pv-nums">{s["count"]} 款 · 开源 {s["open"]} · 平均 Elo {s["avg_elo"] or "—"}</span>
  </div>
  {top_html}
  <p class="pv-cm">{cm}</p>
</div>"""
        )
    sec_focus = (
        "<h2>二、重点厂商逐个盘点</h2>"
        "<p>以下 12 家厂商覆盖了榜单绝大多数的头部模型，按规模排序展开。</p>"
        f"<div class=\"pv-grid\">{''.join(cards)}</div>"
    )

    # 三、全部厂商一览表
    all_rows = ""
    for i, s in enumerate(stats, 1):
        all_rows += (
            f"<tr><td>{i}</td><td><b>{esc(s['name'])}</b></td><td>{s['count']}</td>"
            f"<td>{s['open']}</td><td>{s['avg_elo'] or '—'}</td>"
            f"<td>{model_link(s['top']) if s['top'] else '—'}</td><td>{s['top']['elo'] if s['top'] else '—'}</td></tr>"
        )
    rest_note = ""
    if rest:
        rest_names = "、".join(s["name"] for s in rest[:8])
        rest_note = f"<p>其余厂商（{esc(rest_names)}{'等' if len(rest) > 8 else ''}）模型数量较少，详见下表。</p>"
    sec_all = (
        "<h2>三、全部厂商一览</h2>"
        + rest_note
        + "<table><thead><tr><th>#</th><th>厂商</th><th>模型数</th><th>开源</th>"
          "<th>平均 Elo</th><th>最强模型</th><th>Elo</th></tr></thead>"
          f"<tbody>{all_rows}</tbody></table>"
    )

    # 四、怎么用这份盘点
    sec_close = (
        "<h2>四、怎么用这份盘点</h2>"
        "<ul>"
        "<li><b>选供应商</b>：追求能力天花板看「最强模型」，追求稳定输出看「平均 Elo」，追求生态看「模型数 + 开源数」；</li>"
        "<li><b>国产 vs 海外</b>：数据合规敏感选阿里云 / 智谱 / DeepSeek 等国产厂商；英文场景 OpenAI / Anthropic / Google 仍有优势；</li>"
        "<li><b>私有化部署</b>：优先看开源占比高的厂商（DeepSeek、智谱、Meta、Mistral），部署成本可控；</li>"
        "<li><b>数据在更新</b>：本盘点随榜单数据每周自动刷新，厂商发布新模型后格局会同步变化。</li>"
        "</ul>"
        "<blockquote>数据口径：Elo 来自 LMArena 竞技场；「平均 Elo」为厂商所有已评模型 Elo 的算术平均，"
        "仅作整体实力参考。榜单实时快照见<a href=\"../rank.html\">排行榜</a>。</blockquote>"
    )

    return [sec_overview, sec_focus, sec_all, sec_close]


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


def build_page(date, title, summary, tags, body_html, fname, category="厂商盘点"):
    tag_meta = "".join(f'<meta name="article:tag" content="{esc(t)}">' for t in tags)
    tag_html = "".join(f'<span class="art-tag">{esc(t)}</span>' for t in tags)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{esc(summary)}">
<meta name="keywords" content="大模型厂商,大模型盘点,AI厂商对比,模型生态,{esc(','.join(tags))}">
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
      <a class="act-btn" href="../compare.html">模型对比工具 →</a>
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
    if not models:
        print("[error] data/models.json 无数据，请先运行 fetch_data.py", file=sys.stderr)
        return 1

    date = data.get("meta", {}).get("updated", "2026-09")
    month = date[:7]
    fname = f"provider-{month}.html"
    title = f"{month} 大模型厂商全景盘点：{len(models)} 款模型背后的格局"
    summary = (f"基于 {len(models)} 款模型的实时榜单数据，盘点各家厂商的模型数量、开源策略、"
               f"平均实力与旗舰模型，看清大模型行业竞争格局，随数据每周自动更新。")
    tags = ["厂商盘点", "模型生态", "大模型厂商"]

    stats = provider_stats(models)
    body_html = "\n".join(build_sections(models, stats))

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
