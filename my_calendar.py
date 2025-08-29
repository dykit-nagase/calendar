#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import math
import os
from datetime import date, datetime, timedelta, timezone

# ====== 設定 ======
OUTPUT_SVG = "calendar.svg"
OUTPUT_PNG = "calendar.png"
DATA_JSON = "vacation_data.json"  # GASから保存されたJSON

# 日本語表示
WEEKDAYS_JP = ["日", "月", "火", "水", "木", "金", "土"]

# レイアウト
WIDTH = 1200
HEIGHT = 800
MARGIN = 20
HEADER_H = 70
WEEKDAY_H = 30
CELL_W = (WIDTH - MARGIN * 2) / 7
CELL_H = (HEIGHT - MARGIN * 2 - HEADER_H - WEEKDAY_H) / 6

# 休日配色
SUNDAY_BG = "#fde2e2"
SATURDAY_BG = "#e5f1ff"
TODAY_BG = "#fff8b3"

# イベント色（人物で色分けしたいときに増やしていく）
EVENT_COLORS = [
    "#cfe8ff",  # light blue
    "#ffc7ce",  # light pink
    "#d5f5e3",  # light green
    "#f9e79f",  # light yellow
    "#f5cba7",  # light orange
]

# ====== ユーティリティ ======
def parse_iso(dt_str: str) -> datetime:
    # "2025-08-11T15:00:00.000Z" → ISO対応
    s = dt_str.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        # 末尾にタイムゾーンが無い簡易形にも対応
        return datetime.fromisoformat(s.split(".")[0])

def month_range(y: int, m: int):
    first = date(y, m, 1)
    if m == 12:
        nxt = date(y + 1, 1, 1)
    else:
        nxt = date(y, m + 1, 1)
    last = nxt - timedelta(days=1)
    return first, last

def to_local_d(d: datetime) -> date:
    # 文字化けの主因はフォントだが、日付はUTC起点JSONでもズレないように日付へ変換
    return (d.astimezone(timezone.utc)).date()

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

# ====== SVG ビルド ======
def svg_header(title_text: str) -> str:
    # CJK を確実に解決できるフォント群を先頭に
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}">
  <style>
    @charset "UTF-8";
    .title {{
      font-family: "Noto Sans CJK JP","Noto Sans JP","IPAexGothic",
                   "Yu Gothic","Hiragino Kaku Gothic ProN",sans-serif;
      font-size: 28px; font-weight: 700; fill: #333;
    }}
    .weekday, .day-number, .event, .small {{
      font-family: "Noto Sans CJK JP","Noto Sans JP","IPAexGothic",
                   "Yu Gothic","Hiragino Kaku Gothic ProN",sans-serif;
      fill: #222;
    }}
    .weekday {{ font-size: 16px; font-weight: 600; }}
    .day-number {{ font-size: 14px; }}
    .event {{ font-size: 14px; }}
    .small {{ font-size: 12px; fill: #666; }}
    .cell {{ fill: #fff; stroke: #ddd; }}
  </style>
  <rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" fill="#fff"/>
  <text class="title" x="{MARGIN}" y="{MARGIN + 40}">{title_text}</text>
'''

def svg_footer() -> str:
    return "</svg>\n"

def draw_weekdays():
    parts = []
    y = MARGIN + HEADER_H
    for i, w in enumerate(WEEKDAYS_JP):
        x = MARGIN + i * CELL_W
        parts.append(f'<text class="weekday" x="{x + 8}" y="{y + 22}">{w}</text>')
    return "\n".join(parts)

def month_matrix(y: int, m: int):
    first, last = month_range(y, m)
    first_w = first.weekday()  # Mon=0..Sun=6
    # 日本式（日曜始まり）に合わせる：日=0..土=6
    # Pythonのweekday: 月0..日6 → 日曜始まりのインデックス
    def dow_jp(d: date):
        return (d.weekday() + 1) % 7

    cells = []
    d = first
    start_idx = dow_jp(first)
    # 6行×7列
    for r in range(6):
        row = []
        for c in range(7):
            idx = r * 7 + c
            if idx < start_idx or (d > last):
                row.append(None)
            else:
                row.append(d)
                d = d + timedelta(days=1)
        cells.append(row)
    return cells

def day_bg_color(d: date):
    wd = (d.weekday() + 1) % 7  # 日曜=0
    if wd == 0:
        return SUNDAY_BG
    if wd == 6:
        return SATURDAY_BG
    return "#ffffff"

def draw_grid(y: int, m: int, today: date, cells):
    parts = []
    top = MARGIN + HEADER_H + WEEKDAY_H
    for r in range(6):
        for c in range(7):
            x = MARGIN + c * CELL_W
            y0 = top + r * CELL_H
            d = cells[r][c]
            fill = "#ffffff"
            if d:
                fill = day_bg_color(d)
                if d == today:
                    fill = TODAY_BG
            parts.append(f'<rect class="cell" x="{x}" y="{y0}" width="{CELL_W}" height="{CELL_H}" fill="{fill}" stroke="#ddd"/>')
            if d:
                parts.append(f'<text class="day-number" x="{x + CELL_W - 22}" y="{y0 + 18}">{d.day}</text>')
    return "\n".join(parts)

def load_events(path: str, y: int, m: int):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    first, last = month_range(y, m)
    evs = []
    for ev in data:
        # 期待するキー: start, end, name, title
        try:
            st = parse_iso(ev["start"])
            en = parse_iso(ev["end"])
            nm = ev.get("name", "")
            tt = ev.get("title", "")
        except Exception:
            continue

        sd = to_local_d(st)
        ed = to_local_d(en)
        # 逆順や同日終了の安全化
        if ed < sd:
            sd, ed = ed, sd

        # 月内と交差するものだけ
        f_d, l_d = first, last
        if ed < f_d or sd > l_d:
            continue

        evs.append({
            "start": max(sd, f_d),
            "end": min(ed, l_d),
            "name": nm,
            "title": tt
        })
    return evs

def draw_events(y: int, m: int, cells, events):
    """
    各週（行）ごとに、その週に跨るイベントを帯状に描画。
    同一週内で縦方向にスタックする。
    """
    parts = []
    top = MARGIN + HEADER_H + WEEKDAY_H
    lane_h = 18  # 1イベント帯の高さ
    lane_pad = 3

    # 週ごとに帯レーンを管理
    for r in range(6):
        # その週の開始・終了日
        week_days = [cells[r][c] for c in range(7) if cells[r][c] is not None]
        if not week_days:
            continue
        w_start = week_days[0]
        w_end = week_days[-1]

        # その週に重なるイベント抽出
        week_evs = []
        for ev in events:
            if ev["end"] < w_start or ev["start"] > w_end:
                continue
            # 週内の表示区間
            ds = max(ev["start"], w_start)
            de = max(ds, min(ev["end"], w_end))
            week_evs.append({**ev, "ds": ds, "de": de})

        # レーン割り付け（単純貪欲）
        lanes = []  # 各レーンの末尾終了日
        placed = []
        for ev in sorted(week_evs, key=lambda e: (e["ds"], e["de"])):
            placed_lane = None
            for li, lend in enumerate(lanes):
                if ev["ds"] > lend:
                    placed_lane = li
                    lanes[li] = ev["de"]
                    break
            if placed_lane is None:
                lanes.append(ev["de"])
                placed_lane = len(lanes) - 1
            placed.append((placed_lane, ev))

        # 描画
        y0 = top + r * CELL_H
        for idx, (li, ev) in enumerate(placed):
            color = EVENT_COLORS[(hash(ev["name"]) % len(EVENT_COLORS))]
            # x座標計算
            def day_to_x(d: date):
                c = (d.weekday() + 1) % 7  # 日=0..土=6
                # 週の最初のセルの列を求める
                # cells[r][*] の中で day == d の列を見つける
                for cc in range(7):
                    if cells[r][cc] == d:
                        col = cc
                        break
                else:
                    # 同週内に確実に居るはずだが、念のため推測（列）
                    col = (d.weekday() + 1) % 7
                return MARGIN + col * CELL_W

            x_s = day_to_x(ev["ds"])
            x_e = day_to_x(ev["de"]) + CELL_W
            band_y = y0 + 22 + li * (lane_h + lane_pad)
            h = lane_h
            w = clamp(x_e - x_s - 3, 10, WIDTH)  # 右罫線に被らないよう微調整
            parts.append(f'<rect x="{x_s + 2}" y="{band_y}" width="{w}" height="{h}" fill="{color}" stroke="#b0b0b0"/>')
            label = f'{ev["name"]}: {ev["title"]}'.strip(": ")
            parts.append(f'<text class="event" x="{x_s + 6}" y="{band_y + h - 4}">{escape_xml(label)}</text>')
    return "\n".join(parts)

def escape_xml(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def main():
    # 対象年月（環境変数で上書き可）
    today = date.today()
    y = int(os.environ.get("TARGET_YEAR", today.year))
    m = int(os.environ.get("TARGET_MONTH", today.month))

    first, last = month_range(y, m)
    title_text = f"{y}年 {m}月"

    cells = month_matrix(y, m)
    events = load_events(DATA_JSON, y, m)

    # SVG 組み立て
    parts = [svg_header(title_text)]
    parts.append(draw_weekdays())
    parts.append(draw_grid(y, m, today, cells))
    parts.append(draw_events(y, m, cells, events))
    parts.append(svg_footer())
    svg = "\n".join(parts)

    with open(OUTPUT_SVG, "w", encoding="utf-8") as f:
        f.write(svg)

    # PNG 変換（CairoSVG）
    try:
        import cairosvg
        cairosvg.svg2png(url=OUTPUT_SVG, write_to=OUTPUT_PNG, output_width=WIDTH, output_height=HEIGHT, dpi=192)
        print(f"Generated: {OUTPUT_SVG}, {OUTPUT_PNG}")
    except Exception as e:
        # 失敗してもワークフローを壊さない
        print("PNG rendering failed:", e)
        print(f"SVG only: {OUTPUT_SVG}")

if __name__ == "__main__":
    main()
