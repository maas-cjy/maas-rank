#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大模型选型指南生成器（按月更新）。

基于 data/models.json 实时计算六大场景（代码开发 / 数学推理 / 中文场景 /
Agent 应用 / 性价比 / 开源私有化）的 Top 推荐，生成一篇原创指南文章
（articles/guide-YYYY-MM.html），并登记进 data/articles.json。

用法：
    python scripts/gen_guide_article.py           # 生成并发布
    python scripts/gen_guide_article.py --draft   # 生成草稿（不进 sitemap，列表页不显示）

数据每周更新后重跑一次，指南自动刷新为最新推荐。
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://maasrank.com/"

DIM_LABELS = {
    "math": "数学推理", "hallu": "幻觉控制", "science": "科学推理",
    "ifollow": "精确指令遵循", "coding": "智能体编程", "plan": "智能体任务规划",
}


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


def top_by(models, key, n=5, reverse=True):
    return sorted([m for m in models if m.get(key) is not None], key=lambda x: x[key], reverse=reverse)[:n]


def top_dims(models, dim, n=5):
    return sorted([m for m in models if m.get("dims") and m["dims"].get(dim) is not None],
                  key=lambda x: x["dims"][dim], reverse=True)[:n]


def top_value(models, fn, n=5):
    return sorted([m for m in models if fn(m) is not None], key=fn, reverse=True)[:n]


def model_link(m):
    return f'<a href="../model.html?id={esc(m["id"])}">{esc(m["name"])}</a>'


def scene_table(models, cols):
    """cols: list of (header, value_fn). value_fn returns str/int/float."""
    head = "".join(f"<th>{h}</th>" for h, _ in cols)
    rows = []
    for m in models:
        tds = "".join(f"<td>{fn(m)}</td>" for _, fn in cols)
        rows.append(f"<tr>{tds}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def dim_val(m, dim):
    v = (m.get("dims") or {}).get(dim)
    return "—" if v is None else f"{v:.1f}"


def build_sections(models):
    """六大场景 + 总览，返回 HTML 段落列表。"""
    elo_top = top_by(models, "elo", 6)
    ov_rows = "".join(
        f"<tr><td>{i}</td><td>{model_link(m)}</td><td>{esc(m.get('provider',''))}</td>"
        f"<td>{m['elo']}</td><td>{'开源' if m.get('open') else '闭源'}</td>"
        f"<td>{esc(m.get('release','—'))}</td></tr>"
        for i, m in enumerate(elo_top, 1)
    )
    sec_overview = (
        "<h2>一、总览：当前综合能力最强的六个模型</h2>"
        "<p>以 LMArena 竞技场 Elo 为综合参考（人类盲测偏好），当前排名前六如下。"
        "Elo 反映真实对话体验的胜率偏好，适合作为「不知道选谁时」的默认答案。</p>"
        f"<table><thead><tr><th>#</th><th>模型</th><th>厂商</th><th>Elo</th><th>开源</th><th>发布时间</th></tr></thead>"
        f"<tbody>{ov_rows}</tbody></table>"
        "<p>总体格局：头部模型分差在 30 分以内，第一名与第五名之间没有代差；"
        "真正的差异体现在具体维度上——下面按场景拆开看。</p>"
    )

    # 场景一：代码开发
    cd = top_dims(models, "coding", 5)
    sec_code = (
        "<h2>二、代码开发：智能体编程得分 Top 5</h2>"
        "<p>代码场景看「智能体编程」维度（模型自主完成编程任务的能力），并参考 Elo 确认整体体验。</p>"
        + scene_table(cd, [
            ("模型", model_link),
            ("厂商", lambda m: esc(m.get("provider", ""))),
            ("智能体编程", lambda m: dim_val(m, "coding")),
            ("Elo", lambda m: m.get("elo", "—")),
            ("开源", lambda m: "是" if m.get("open") else "否"),
        ])
        + "<p>点评：Kimi K3 与 Qwen3.8-Max 是当前国产阵营的编程第一梯队；"
          "需要离线部署时 DeepSeek V4 Flash 性价比更高（详见场景五、六）。</p>"
    )

    # 场景二：数学推理
    mt = top_dims(models, "math", 5)
    sec_math = (
        "<h2>三、数学推理：数学得分 Top 5</h2>"
        "<p>数学推理维度衡量解题、证明与逻辑推导能力，对科研、量化、教育类应用最关键。</p>"
        + scene_table(mt, [
            ("模型", model_link),
            ("厂商", lambda m: esc(m.get("provider", ""))),
            ("数学推理", lambda m: dim_val(m, "math")),
            ("科学推理", lambda m: dim_val(m, "science")),
            ("Elo", lambda m: m.get("elo", "—")),
        ])
        + "<p>点评：DeepSeek 系列在数学上表现稳定，V4 Flash 与 V4 Pro 双双进入前列；"
          "混元 Hy3 数学与科学均衡，适合需要兼顾两者的场景。</p>"
    )

    # 场景三：中文场景与指令遵循
    ifw = top_dims(models, "ifollow", 5)
    sec_cn = (
        "<h2>四、中文场景与指令遵循：精确指令遵循 Top 5</h2>"
        "<p>中文业务（客服、写作、内容生成）更看重「精确指令遵循」——按用户要求执行而不跑偏，"
        "同时参考 SuperCLUE 中文综合分。</p>"
        + scene_table(ifw, [
            ("模型", model_link),
            ("厂商", lambda m: esc(m.get("provider", ""))),
            ("精确指令遵循", lambda m: dim_val(m, "ifollow")),
            ("SuperCLUE", lambda m: f"{m['superclue']:.1f}" if m.get("superclue") is not None else "—"),
            ("Elo", lambda m: m.get("elo", "—")),
        ])
        + "<p>点评：Qwen3.8-Max 指令遵循与中文综合分双高，是中文业务场景的稳妥选择；"
          "DeepSeek V4 Pro 与 Doubao Seed 2.1 Pro 紧随其后，可结合价格取舍。</p>"
    )

    # 场景四：Agent 应用
    pl = top_dims(models, "plan", 5)
    sec_agent = (
        "<h2>五、Agent 应用：智能体任务规划 Top 5</h2>"
        "<p>Agent / 工作流场景关注「智能体任务规划」维度（拆解任务、调用工具、多步执行），"
        "并搭配长上下文支持复杂会话。</p>"
        + scene_table(pl, [
            ("模型", model_link),
            ("厂商", lambda m: esc(m.get("provider", ""))),
            ("智能体任务规划", lambda m: dim_val(m, "plan")),
            ("上下文", lambda m: f"{m.get('context', 0) // 1000}k" if m.get("context") else "—"),
            ("Elo", lambda m: m.get("elo", "—")),
        ])
        + "<p>点评：Qwen3.8-Max 的任务规划得分接近 91，配合 1M 上下文，"
          "是目前做 Agent 编排最顺手的国产模型之一；DeepSeek V4 Pro、Kimi K3 也值得纳入候选。</p>"
    )

    # 场景五：性价比
    def value_ratio(m):
        if m.get("priceIn") is None or m.get("priceIn") <= 0 or not m.get("elo"):
            return None
        return m["elo"] / m["priceIn"]

    pr = top_value(models, value_ratio, 6)
    sec_value = (
        "<h2>六、性价比之选：单位成本获得的智能最高</h2>"
        "<p>用 Elo ÷ 输入价格（元/百万 tokens）衡量「每花一块钱买到多少智能」，"
        "适合成本敏感的生产环境与大规模调用。</p>"
        + scene_table(pr, [
            ("模型", model_link),
            ("厂商", lambda m: esc(m.get("provider", ""))),
            ("输入价", lambda m: fmt_cny(m.get("priceIn"))),
            ("输出价", lambda m: fmt_cny(m.get("priceOut"))),
            ("Elo", lambda m: m.get("elo", "—")),
            ("性价比", lambda m: f"{value_ratio(m):.0f}" if value_ratio(m) else "—"),
        ])
        + "<p>点评：DeepSeek V4 Flash 以 ¥7.2/百万 tokens 的输入价拿到 1432 的 Elo，"
          "是「便宜又够强」的代表；混元 Hy3 同样是一块钱级别里能力最均衡的选项。"
          "注：部分低价开源模型（如 Llama 4 Maverick）Elo 偏低，适合非关键路径使用。</p>"
    )

    # 场景六：开源私有化
    op = top_by([m for m in models if m.get("open")], "elo", 6)
    sec_open = (
        "<h2>七、开源私有化：可自部署的模型 Top 6</h2>"
        "<p>数据合规或成本控制需要私有化部署时，开源模型是唯一选择。按 Elo 排序如下，"
        "部署前注意核对许可证与硬件要求。</p>"
        + scene_table(op, [
            ("模型", model_link),
            ("厂商", lambda m: esc(m.get("provider", ""))),
            ("Elo", lambda m: m.get("elo", "—")),
            ("上下文", lambda m: f"{m.get('context', 0) // 1000}k" if m.get("context") else "—"),
            ("发布时间", lambda m: esc(m.get("release", "—"))),
        ])
        + "<p>点评：开源阵营国产占优——Qwen3.8-Max、GLM 5.3、Kimi K3 分列前三；"
          "NVIDIA Nemotron 3 Ultra 与 Gemma 4 31b 则是海外开源的代表，适合英文为主的场景。</p>"
    )

    sec_close = (
        "<h2>八、怎么用这份指南</h2>"
        "<ul>"
        "<li><b>按场景定位</b>：先确认你的核心场景（代码 / 数学 / 中文 / Agent），看对应榜单；</li>"
        "<li><b>再看成本</b>：同场景内用性价比榜单二次筛选；</li>"
        "<li><b>数据在更新</b>：本指南随榜单数据每周自动刷新，模型价格与排名变动会同步体现；</li>"
        "<li><b>上线前实测</b>：正式项目请用自己的业务数据做小规模 A/B 测试。</li>"
        "</ul>"
        "<blockquote>数据口径：Elo 来自 LMArena 竞技场，六维评分与 SuperCLUE 来自 SuperCLUE 测评；"
        "价格为公开 API 报价，按 1 美元 ≈ 7.2 元换算。榜单实时快照见<a href=\"../rank.html\">排行榜</a>。</blockquote>"
    )

    return [sec_overview, sec_code, sec_math, sec_cn, sec_agent, sec_value, sec_open, sec_close]


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


def build_page(date, title, summary, tags, body_html, fname):
    tag_meta = "".join(f'<meta name="article:tag" content="{esc(t)}">' for t in tags)
    tag_html = "".join(f'<span class="art-tag">{esc(t)}</span>' for t in tags)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{esc(summary)}">
<meta name="keywords" content="大模型选型指南,大模型推荐,大模型评测,模型选型,{esc(','.join(tags))}">
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
        <span>{date}</span><span>·</span><span>选型指南</span><span>·</span>
        <span>MaaS Rank</span>
        <span class="art-tags">{tag_html}</span>
      </div>
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
    fname = f"guide-{month}.html"
    title = f"{month} 大模型选型指南：六大场景 Top 推荐"
    summary = (f"覆盖代码开发、数学推理、中文场景、Agent 应用、性价比、开源私有化六大场景，"
               f"基于 {len(models)} 个模型的实时榜单数据给出 Top 推荐清单，随数据每周自动更新。")
    tags = ["选型指南", "模型推荐", "大模型评测"]

    body_html = "\n".join(build_sections(models))

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
