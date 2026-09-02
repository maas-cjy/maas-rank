#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 MaaS Rank 品牌 OG 分享图（1200x630 PNG）。

视觉规范与站点一致：深紫 #1E1B4B 背景 + 白 M logo + 紫色柱状条（#8B5CF6）。
"""
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
BG = (30, 27, 75)          # #1E1B4B
PANEL = (60, 53, 116)      # 装饰面板描边 #3C3489 附近
BAR = (67, 50, 135)        # #8B5CF6 35% 叠加背景
BAR_BRIGHT = (83, 77, 221) # #7F77DD
LOGO_BG = (38, 36, 89)     # #26215C
ACCENT = (139, 92, 246)    # #8B5CF6
TITLE = (255, 255, 255)
SUB = (174, 169, 236)      # #AFA9EC
MUTED = (206, 203, 246)    # #CECBF6
DIM = (127, 119, 221)      # #7F77DD

ARIAL_B = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
ARIAL = "/System/Library/Fonts/Supplemental/Arial.ttf"
HIRAGINO = "/System/Library/Fonts/Hiragino Sans GB.ttc"

def font(path, size, index=0):
    return ImageFont.truetype(path, size, index=index)

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# --- 右侧装饰：数据柱状图面板 ---
px0, py0, pw, ph = 700, 78, 505, 524
d.rounded_rectangle([px0, py0, px0 + pw, py0 + ph], radius=24,
                    outline=PANEL, width=2)
bars = [150, 215, 280, 345, 410, 470]
bw, step = 50, 66
for i, h in enumerate(bars):
    x = px0 + 52 + i * step
    y_top = py0 + ph - 24 - h
    col = BAR_BRIGHT if i >= 4 else BAR
    d.rounded_rectangle([x, y_top, x + bw, py0 + ph - 24], radius=8, fill=col)
    # 柱顶亮点
    d.rounded_rectangle([x, y_top - 5, x + bw, y_top - 1], radius=2, fill=SUB)
# 面板底部一条基准线
d.rounded_rectangle([px0 + 52, py0 + ph - 24, px0 + pw - 52, py0 + ph - 20],
                    radius=2, fill=DIM)

# --- 左侧内容 ---
# logo：圆角底 + 白 M + 紫色柱条
lx, ly, lsize = 88, 240, 104
d.rounded_rectangle([lx, ly, lx + lsize, ly + lsize], radius=26,
                    fill=LOGO_BG, outline=ACCENT, width=3)
# M 字母居中
f_m = font(ARIAL_B, 54)
bbox = d.textbbox((0, 0), "M", font=f_m)
m_w = bbox[2] - bbox[0]
m_x = lx + (lsize - m_w) / 2 - bbox[0] - 30   # 偏左，右侧留给柱条
m_y = ly + (lsize - 54) / 2 - 6
d.text((m_x, m_y), "M", font=f_m, fill=TITLE)
# 三根柱条（对应 logo.svg 视觉）
bar_x = lx + 58
heights = [18, 29, 40]
for i, h in enumerate(heights):
    bx = bar_x + i * 11
    d.rounded_rectangle([bx, ly + 78 - h, bx + 7, ly + 78], radius=3, fill=ACCENT)

# 品牌名
f_title = font(ARIAL_B, 72)
d.text((lx + lsize + 36, 250), "MaaS Rank", font=f_title, fill=TITLE)

# 中文副标题
f_sub = font(HIRAGINO, 38, index=2)
d.text((lx + lsize + 36, 336), "大模型 API 排行榜", font=f_sub, fill=SUB)

# 分隔条
d.rounded_rectangle([lx + lsize + 36, 398, lx + lsize + 36 + 64, 398 + 6],
                    radius=3, fill=ACCENT)

# 数据点说明
f_body = font(HIRAGINO, 26, index=0)
d.text((lx + lsize + 36, 436),
       "LMArena Elo 竞技场 · SuperCLUE 中文能力 · 厂商官方 API 价格",
       font=f_body, fill=MUTED)

# 底部：URL（左）+ 每周更新（右）
f_url = font(ARIAL, 24)
d.text((lx, 552), "maasrank.com", font=f_url, fill=DIM)
f_tip = font(HIRAGINO, 24, index=2)
tip = "数据每周自动更新"
tw = d.textlength(tip, font=f_tip)
d.text((W - 88 - tw, 552), tip, font=f_tip, fill=MUTED)
# 右下角小柱条装饰
tx = W - 88 - tw - 54
for i, h in enumerate([10, 16, 22]):
    d.rounded_rectangle([tx + i * 12, 568 - h, tx + i * 12 + 8, 568],
                        radius=3, fill=ACCENT)

out = "/Users/yy/WorkBuddy/2026-08-19-11-07-29/maas-rank/assets/og-image.png"
img.save(out, "PNG")
print("saved:", out, img.size)
