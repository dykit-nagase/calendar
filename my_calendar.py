#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from datetime import date, datetime, timedelta, timezone
import hashlib


# ====== 出力ファイル ======
OUTPUT_SVG = "calendar.svg"
OUTPUT_PNG = "calendar.png"
DATA_JSON = "vacation_data.json"  # GAS で保存した JSON（start/end/name/title）

# ====== 表示設定 ======
WIDTH = 1200
HEIGHT = 1200
MARGIN = 20
HEADER_H = 70
WEEKDAY_H = 30
ROWS = 4            # 4週間分（前1週 + 実行週 + 次2週）
COLS = 7            # 日〜土

CELL_W = (WIDTH - MARGIN * 2) / COLS
CELL_H = (HEIGHT - MARGIN * 2 - HEADER_H - WEEKDAY_H) / ROWS

WEEKDAYS_JP = ["日", "月", "火", "水", "木", "金", "土"]

SUNDAY_BG = "#fff7f9"
SATURDAY_BG = "#f7f7ff"
TODAY_BG = "#d9ffeb"

EVENT_COLORS = [
    "#cfe8ff", "#ffc7ce", "#d5f5e3", "#f9e79f", "#f5cba7",
    "#e8daef", "#d6eaf8", "#fdebd0", "#f6ddcc", "#d1f2eb", "#fef9e7",
]

_name_color_cache = {}
def color_for_person(raw_name: str) -> str:
    name = (raw_name or "").strip()
    if not name:
        name = "(no-name)"  # 空なら共通のキーに
    if name not in _name_color_cache:
        h = hashlib.md5(name.encode("utf-8")).hexdigest()
        idx = int(h[:8], 16) % len(EVENT_COLORS)
        _name_color_cache[name] = EVENT_COLORS[idx]
    return _name_color_cache[name]

# ====== ユーティリティ ======
def parse_iso(dt_str: str) -> datetime:
    s = dt_str.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.fromisoformat(s.split(".")[0])

def to_utc_date(dt: datetime) -> date:
    return dt.astimezone(timezone.utc).date()

def start_of_week_sunday(d: date) -> date:
    # Python: Monday=0..Sunday=6 → 日曜=0..土曜=6 に合わせて補正
    dow_jp = (d.weekday() + 1) % 7
    return d - timedelta(days=dow_jp)

def day_bg_color(d: date):
    wd = (d.weekday() + 1) % 7
    if wd == 0:
        return SUNDAY_BG
    if wd == 6:
        return SATURDAY_BG
    return "#ffffff"

def escape_xml(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ====== データ読み込み ======
def load_events_range(path: str, start_d: date, end_d: date):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    events = []
    for ev in data:
        try:
            st = to_utc_date(parse_iso(ev["start"]))
            en = to_utc_date(parse_iso(ev["end"]))
        except Exception:
            continue
        if en < st:
            st, en = en, st
        # 可視範囲と交差するものだけ
        if en < start_d or st > end_d:
            continue
        events.append({
            "start": max(st, start_d),
            "end": min(en, end_d),
            "name": ev.get("name", ""),
            "title": ev.get("title", ""),
        })
    return events

# ====== SVG ======
def svg_header(title_text: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}">
  <style>
    @charset "UTF-8";
    .title {{
      font-family: "Noto Sans CJK JP","Noto Sans JP","IPAexGothic",
                   "Yu Gothic","Hiragino Kaku Gothic ProN",sans-serif;
      font-size: 28px; font-weight: 700; fill: #333;
    }}
    .weekday, .day-number, .event {{
      font-family: "Noto Sans CJK JP","Noto Sans JP","IPAexGothic",
                   "Yu Gothic","Hiragino Kaku Gothic ProN",sans-serif;
      fill: #222;
    }}
    .weekday {{ font-size: 16px; font-weight: 600; }}
    .day-number {{ font-size: 14px; }}
    .event {{ font-size: 14px; }}
    .cell {{ fill: #fff; stroke: #ddd; }}
  </style>
  <rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" fill="#fff"/>
  <text class="title" x="{MARGIN}" y="{MARGIN + 40}">{title_text}</text>
'''

def svg_footer() -> str:
    return "</svg>\n"

def draw_weekdays(y_base: float):
    parts = []
    for i, w in enumerate(WEEKDAYS_JP):
        x = MARGIN + i * CELL_W
        parts.append(f'<text class="weekday" x="{x + 8}" y="{y_base + 22}">{w}</text>')
    return "\n".join(parts)

def build_matrix(start_d: date, rows: int, cols: int):
    # 連続する rows*cols 日のマトリクス
    days = [start_d + timedelta(days=i) for i in range(rows * cols)]
    matrix = [days[r*cols:(r+1)*cols] for r in range(rows)]
    return matrix

def draw_grid(matrix, today: date):
    parts = []
    top = MARGIN + HEADER_H + WEEKDAY_H
    for r in range(ROWS):
        for c in range(COLS):
            x = MARGIN + c * CELL_W
            y0 = top + r * CELL_H
            d = matrix[r][c]
            fill = day_bg_color(d)
            if d == today:
                fill = TODAY_BG
            parts.append(f'<rect x="{x}" y="{y0}" width="{CELL_W}" height="{CELL_H}" fill="{fill}" stroke="#ddd"/>')
            parts.append(f'<text class="day-number" x="{x + CELL_W - 22}" y="{y0 + 18}">{d.day}</text>')
    return "\n".join(parts)

def draw_events(matrix, events):
    """
    週（行）ごとにイベント帯をレーンに積んで描画。
    """
    parts = []
    top = MARGIN + HEADER_H + WEEKDAY_H
    lane_h = 18
    lane_pad = 3

    for r in range(ROWS):
        row_days = matrix[r]
        w_start, w_end = row_days[0], row_days[-1]

        # 週にかかるイベント抽出
        week_evs = []
        for ev in events:
            if ev["end"] < w_start or ev["start"] > w_end:
                continue
            ds = max(ev["start"], w_start)
            de = max(ds, min(ev["end"], w_end))
            week_evs.append({**ev, "ds": ds, "de": de})

        # レーン割当（貪欲）
        lanes = []
        placed = []
        for ev in sorted(week_evs, key=lambda e: (e["ds"], e["de"])):
            placed_lane = None
            for i, lend in enumerate(lanes):
                if ev["ds"] > lend:
                    placed_lane = i
                    lanes[i] = ev["de"]
                    break
            if placed_lane is None:
                lanes.append(ev["de"])
                placed_lane = len(lanes) - 1
            placed.append((placed_lane, ev))

        y0 = top + r * CELL_H
        for li, ev in placed:
            color = color_for_person(ev.get("name") or ev.get("title") or "")

            def day_to_x(d: date):
                c = (d.weekday() + 1) % 7  # 日=0..土=6
                # 行内の日付→列位置を直接求める
                for cc in range(7):
                    if matrix[r][cc] == d:
                        col = cc
                        break
                else:
                    col = c
                return MARGIN + col * CELL_W

            x_s = day_to_x(ev["ds"])
            x_e = day_to_x(ev["de"]) + CELL_W
            band_y = y0 + 22 + li * (lane_h + lane_pad)
            w = max(10, x_e - x_s - 3)
            parts.append(f'<rect x="{x_s + 2}" y="{band_y}" width="{w}" height="{lane_h}" fill="{color}" stroke="#b0b0b0"/>')
            label = f'{ev["name"]}: {ev["title"]}'.strip(": ")
            parts.append(f'<text class="event" x="{x_s + 6}" y="{band_y + lane_h - 4}">{escape_xml(label)}</text>')
    return "\n".join(parts)

def main():
    today = date.today()

    # 実行日の属する週の先頭（日曜）を求め、前1週間から開始
    this_week_start = start_of_week_sunday(today)
    start_d = this_week_start - timedelta(days=7)         # 前1週
    end_d = this_week_start + timedelta(days=7*3 - 1)     # 次2週の週末（4週分合計）

    # タイトル（範囲を表示）
    title_text = f"{start_d.strftime('%Y-%m-%d')} 〜 {end_d.strftime('%Y-%m-%d')}"

    # マトリクス（4行×7列）
    matrix = build_matrix(start_d, ROWS, COLS)
    events = load_events_range(DATA_JSON, start_d, end_d)

    # SVG
    parts = [svg_header(title_text)]
    parts.append(draw_weekdays(MARGIN + HEADER_H))
    parts.append(draw_grid(matrix, today))
    parts.append(draw_events(matrix, events))
    parts.append(svg_footer())
    svg = "\n".join(parts)

    with open(OUTPUT_SVG, "w", encoding="utf-8") as f:
        f.write(svg)

    # PNG 変換
    try:
        import cairosvg
        cairosvg.svg2png(url=OUTPUT_SVG, write_to=OUTPUT_PNG,
                         output_width=WIDTH, output_height=HEIGHT, dpi=192)
        print(f"Generated: {OUTPUT_SVG}, {OUTPUT_PNG}")
    except Exception as e:
        print("PNG rendering failed:", e)
        print(f"SVG only: {OUTPUT_SVG}")

if __name__ == "__main__":
    main()
