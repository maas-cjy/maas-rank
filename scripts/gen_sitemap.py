#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 sitemap.xml 与 robots.txt。

绑定自定义域名后，只需把下面 SITE_URL 改成你的域名（例如
'https://www.yourdomain.com'）重新运行本脚本即可：

    python scripts/gen_sitemap.py

文章 URL 自动从 data/articles.json 读取，无需手工维护。
"""
import json
import os
import sys
from datetime import date

# ============================================================
# 站点地址配置：绑定自定义域名后改这里（结尾不带斜杠）
# ============================================================
SITE_URL = "https://maas-cjy.github.io/maas-rank"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 主页面：(路径, 更新频率, 权重)
MAIN_PAGES = [
    ("",            "weekly",  "1.0"),
    ("rank.html",   "weekly",  "0.9"),
    ("articles.html", "weekly", "0.8"),
    ("compare.html", "weekly", "0.8"),
    ("model.html",  "weekly",  "0.7"),
    ("report.html", "weekly",  "0.7"),
    ("about.html",  "monthly", "0.6"),
]


def today() -> str:
    return date.today().isoformat()


def main() -> int:
    updated = today()
    meta_path = os.path.join(ROOT, "data", "models.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                updated = json.load(f).get("meta", {}).get("updated") or updated
        except Exception:
            pass

    entries = []
    for path, freq, prio in MAIN_PAGES:
        entries.append((SITE_URL + "/" + path if path else SITE_URL + "/", updated, freq, prio))

    # 文章页
    arts_path = os.path.join(ROOT, "data", "articles.json")
    if os.path.exists(arts_path):
        try:
            with open(arts_path, encoding="utf-8") as f:
                arts = json.load(f)
            for a in arts:
                if a.get("draft"):
                    continue  # 草稿不进 sitemap
                entries.append((f"{SITE_URL}/articles/{a['file']}", a.get("date", updated), "monthly", "0.6"))
        except Exception as e:
            print(f"[warn] 读取 articles.json 失败: {e}", file=sys.stderr)

    urls = "\n".join(
        f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>{lm}</lastmod>\n"
        f"    <changefreq>{freq}</changefreq>\n    <priority>{prio}</priority>\n  </url>"
        for loc, lm, freq, prio in entries
    )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n</urlset>\n"
    )
    with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap)

    robots = (
        "User-agent: *\n"
        "Allow: /\n\n"
        f"Sitemap: {SITE_URL}/sitemap.xml\n"
    )
    with open(os.path.join(ROOT, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(robots)

    print(f"[ok] sitemap.xml: {len(entries)} 个 URL | robots.txt 已生成 | SITE_URL={SITE_URL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
