#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行业观察生成器（月度 + 事件触发，半自动）。

行业观察不是纯数据驱动内容：选题与观点来自行业事件，需要先起草
（AI 搜集素材 + 人工确认），再渲染成页面。本脚本只负责「排版」：

    1. 读取内容源  content/insight/YYYY-MM.md
       （markdown 子集 + front matter：title / summary / date / tags）
    2. 渲染成 articles/insight-YYYY-MM.html（导航 / 统计代码 / 提示条 / 样式齐全）
    3. 登记进 data/articles.json

用法：
    python scripts/gen_insight_article.py                # 生成当月并发布
    python scripts/gen_insight_article.py --month 2026-09
    python scripts/gen_insight_article.py --month 2026-09 --draft   # 草稿（不进 sitemap）

重大事件临时加篇时，把 md 写到 content/insight/2026-09-事件名.md，
再 --file 指定该文件即可（文件名仍按月，页面 URL 不变，当月覆盖更新）。
"""
import argparse
import json
import os
import re
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_DIR = os.path.join(ROOT, "content", "insight")
BASE = "https://maasrank.com/"

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


def esc(s):
    return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def parse_front_matter(text):
    """解析 --- 包裹的 front matter，返回 (meta dict, 正文)。"""
    if text.startswith("---"):
        end = text.find("\n---", 4)
        if end != -1:
            meta = {}
            for line in text[4:end].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            return meta, text[end + 4:].lstrip("\n")
    return {}, text


def md_inline(s):
    """行内格式：**粗体**、[文字](链接)、`代码`。"""
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" rel="nofollow">\1</a>', s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def md_table(lines, i):
    """解析表格块，返回 (HTML, 下一行索引)。lines[i] 为表头行。"""
    head = lines[i]
    if i + 1 >= len(lines) or not re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]):
        return None, i
    cols = [c.strip() for c in head.strip().strip("|").split("|")]
    rows = []
    j = i + 2
    while j < len(lines) and lines[j].strip() and lines[j].strip().startswith("|"):
        cells = [md_inline(c.strip()) for c in lines[j].strip().strip("|").split("|")]
        rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
        j += 1
    th = "".join(f"<th>{esc(c)}</th>" for c in cols)
    html = f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    return html, j


def md_to_html(md_text):
    """极简 markdown → HTML：标题 / 表格 / 列表 / 引用 / 分隔线 / 段落。"""
    lines = md_text.splitlines()
    out = []
    i = 0
    n = len(lines)
    marker = re.compile(r"^\s*(?:[-*+]\s+|\d+\.\s+|>|#|\|)")
    while i < n:
        prev_i = i
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped == "---":
            out.append("<hr>")
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if m:
            lv = len(m.group(1))
            out.append(f"<h{lv}>{md_inline(m.group(2))}</h{lv}>")
            i += 1
            continue
        if stripped.startswith("|"):
            html, j = md_table(lines, i)
            if html:
                out.append(html)
                i = j
                continue
        if re.match(r"^\s*[-*]\s+", stripped) or re.match(r"^\s*\d+\.\s+", stripped):
            items = []
            ordered = bool(re.match(r"^\s*\d+\.\s+", stripped))
            while i < n and lines[i].strip():
                s = lines[i].strip()
                if ordered:
                    mm = re.match(r"^\d+\.\s+(.+)$", s)
                else:
                    mm = re.match(r"^[-*]\s+(.+)$", s)
                if not mm:
                    break
                items.append(f"<li>{md_inline(mm.group(1))}</li>")
                i += 1
            tag = "ol" if ordered else "ul"
            inner = "".join(items)
            out.append(f"<{tag}>" + inner + f"</{tag}>")
            continue
        if stripped.startswith(">"):
            quotes = []
            while i < n and lines[i].strip().startswith(">"):
                quotes.append(md_inline(lines[i].strip()[1:].strip()))
                i += 1
            out.append(f"<blockquote>{''.join(f'<p>{q}</p>' for q in quotes)}</blockquote>")
            continue
        para = []
        while i < n and lines[i].strip() and not marker.match(lines[i].strip()):
            para.append(md_inline(lines[i].strip()))
            i += 1
        out.append("<p>" + " ".join(para) + "</p>")
        if i == prev_i:
            i += 1
    return "\n".join(out)


def build_page(meta, body_html, fname):
    title = meta.get("title", "")
    summary = meta.get("summary", "")
    date_s = meta.get("date", date.today().isoformat())
    tags = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()] or ["行业观察"]
    tag_meta = "".join(f'<meta name="article:tag" content="{esc(t)}">' for t in tags)
    tag_html = "".join(f'<span class="art-tag">{esc(t)}</span>' for t in tags)
    keywords = "大模型行业观察,行业动态,大模型趋势," + ",".join(tags)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{esc(summary)}">
<meta name="keywords" content="{esc(keywords)}">
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
<meta property="article:published_time" content="{date_s}">
{tag_meta}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(summary)}">
<meta name="twitter:image" content="{BASE}assets/og-image.png">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Article","headline":{json.dumps(title, ensure_ascii=False)},"datePublished":"{date_s}","dateModified":"{date_s}","url":"{BASE}articles/{fname}","publisher":{{"@type":"Organization","name":"MaaS Rank"}},"inLanguage":"zh-CN"}}
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
        <span>{date_s}</span><span>·</span><span>行业观察</span><span>·</span>
        <span>MaaS Rank</span>
        <span class="art-tags">{tag_html}</span>
      </div>
      <div class="update-banner">本月更新 · 更新于 {date_s}</div>
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
  <div>MaaS Rank · 大模型排行榜 · 本页更新于 {date_s} · 数据口径见<a href="../about.html">数据说明</a></div>
</footer>

<script src="../js/site.js"></script>
{BAIDU_STAT}
<script src="../js/analytics.js"></script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="行业观察生成器（月度 + 事件触发）")
    ap.add_argument("--month", default=date.today().strftime("%Y-%m"), help="月份，默认当月，如 2026-09")
    ap.add_argument("--file", help="指定 md 内容源（相对 content/insight/ 或绝对路径），默认 <month>.md")
    ap.add_argument("--draft", action="store_true", help="生成草稿（不进 sitemap）")
    args = ap.parse_args()

    month = args.month
    src = args.file or f"{month}.md"
    src_path = src if os.path.isabs(src) else os.path.join(CONTENT_DIR, src)
    if not os.path.exists(src_path):
        print(f"[error] 内容源不存在：{src_path}", file=sys.stderr)
        print("        请先起草 content/insight/YYYY-MM.md（front matter: title/summary/date/tags）", file=sys.stderr)
        return 1

    with open(src_path, encoding="utf-8") as f:
        text = f.read()
    meta, body_md = parse_front_matter(text)
    if not meta.get("title") or not meta.get("summary"):
        print("[error] front matter 缺少 title 或 summary", file=sys.stderr)
        return 1

    body_html = md_to_html(body_md)
    fname = f"insight-{month}.html"
    os.makedirs(os.path.join(ROOT, "articles"), exist_ok=True)
    with open(os.path.join(ROOT, "articles", fname), "w", encoding="utf-8") as f:
        f.write(build_page(meta, body_html, fname))

    entry = {
        "file": fname,
        "title": meta["title"],
        "date": meta.get("date", date.today().isoformat()),
        "issue": None,
        "summary": meta["summary"],
        "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()] or ["行业观察"],
    }
    if args.draft:
        entry["draft"] = True
    articles = []
    ap_ = os.path.join(ROOT, "data", "articles.json")
    if os.path.exists(ap_):
        with open(ap_, encoding="utf-8") as f:
            articles = json.load(f)
    articles = [a for a in articles if a.get("file") != fname]
    articles.insert(0, entry)
    with open(ap_, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[ok] 已生成 articles/{fname}{'（草稿）' if args.draft else ''}")
    print(f"     标题：{meta['title']}")
    print(f"     来源：{src_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
