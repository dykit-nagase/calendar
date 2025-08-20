import json
import requests
from datetime import datetime, timedelta
import pyvips
import os


class CalendarSVGGenerator:
    def __init__(self, cell_width=120, cell_height=140, header_height=40, margin=10, event_height=18):
        self.cell_width = cell_width
        self.cell_height = cell_height
        self.header_height = header_height
        self.margin = margin
        self.event_height = event_height
        self.week_days = ['月', '火', '水', '木', '金', '土', '日']
        self.member_colors = {}
        self.events = []
        
    def get_week_range(self, target_date):
        days_since_monday = target_date.weekday()
        monday = target_date - timedelta(days=days_since_monday)
        
        week_dates = []
        for i in range(7):
            week_dates.append(monday + timedelta(days=i))
        
        return week_dates
    
    def get_four_week_range(self, today=None):
        if today is None:
            today = datetime.now().date()
        
        current_week = self.get_week_range(today)
        prev_week_start = current_week[0] - timedelta(days=7)
        prev_week = self.get_week_range(prev_week_start)
        next_week1_start = current_week[0] + timedelta(days=7)
        next_week1 = self.get_week_range(next_week1_start)
        next_week2_start = current_week[0] + timedelta(days=14)
        next_week2 = self.get_week_range(next_week2_start)
        
        all_weeks = [prev_week, current_week, next_week1, next_week2]
        return all_weeks, today
    
    def load_events_from_json(self, json_file):
        raw_events = []
        members = set()
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                for row in data:
                    # キー名をJSONデータに合わせる
                    start_date_str = row.get('start')
                    end_date_str = row.get('end')
                    member = row.get('name')
                    description = row.get('title')
                    
                    if start_date_str and end_date_str and member and description:
                        # 日付形式をISO 8601に合わせる
                        start_date = datetime.fromisoformat(start_date_str[:-1]).date()
                        end_date = datetime.fromisoformat(end_date_str[:-1]).date()
                        
                        raw_events.append({
                            'start_date': start_date,
                            'end_date': end_date,
                            'member': member,
                            'description': description
                        })
                        members.add(member)
        except FileNotFoundError:
            print(f"Warning: {json_file} not found")
            return
        except Exception as e:
            print(f"JSONファイルの読み込みエラー: {e}")
            return

        self.events = self.remove_duplicate_events(raw_events)
        unique_members = sorted(list(members))
        self.assign_member_colors(unique_members)

    def remove_duplicate_events(self, events):
        event_dict = {}
        for event in events:
            key = (event['member'], event['start_date'], event['end_date'])
            event_dict[key] = event
        
        return list(event_dict.values())
    
    def assign_member_colors(self, members):
        colors = [
            '#ffb3ba', '#bae1ff', '#baffc9', '#ffffba', '#ffdfba', 
            '#e0bbe4', '#d4d4aa', '#ffc9c9', '#c9e4ff', '#d4ffd4', 
            '#ffffe0', '#ffe4e1', '#f0f8ff', '#f0fff0', '#ffefd5', 
            '#e6e6fa', '#f5deb3', '#ffe4b5', '#dda0dd', '#98fb98'
        ]
        
        for i, member in enumerate(members):
            self.member_colors[member] = colors[i % len(colors)]
    
    def get_events_for_date_range(self, start_date, end_date):
        return [event for event in self.events
                if not (event['end_date'] < start_date or event['start_date'] > end_date)]
    
    def calculate_event_layout(self, weeks):
        all_dates = []
        for week in weeks:
            all_dates.extend(week)
        
        start_date = all_dates[0]
        end_date = all_dates[-1]
        
        relevant_events = self.get_events_for_date_range(start_date, end_date)
        
        date_event_positions = {}
        for date in all_dates:
            date_event_positions[date] = []
        
        for event in relevant_events:
            event_dates = []
            current_date = max(event['start_date'], start_date)
            while current_date <= min(event['end_date'], end_date):
                event_dates.append(current_date)
                current_date += timedelta(days=1)
            
            position = 0
            while True:
                can_place = True
                for date in event_dates:
                    if position < len(date_event_positions[date]) and date_event_positions[date][position] is not None:
                        can_place = False
                        break
                
                if can_place:
                    for date in event_dates:
                        while len(date_event_positions[date]) <= position:
                            date_event_positions[date].append(None)
                        date_event_positions[date][position] = event
                    event['layout_position'] = position
                    break
                
                position += 1
        
        return date_event_positions
    
    def generate_svg(self, output_file="calendar.svg", today=None):
        weeks, today_date = self.get_four_week_range(today)
        date_event_positions = self.calculate_event_layout(weeks)
        
        max_events = max([len(positions) for positions in date_event_positions.values()] + [0])
        if max_events > 0:
            self.cell_height = max(120, 60 + max_events * (self.event_height + 2))
        
        total_width = 7 * self.cell_width + 2 * self.margin
        total_height = self.header_height + 4 * self.cell_height + 2 * self.margin
        
        svg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="{total_width}" height="{total_height}" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <style>
            .header {{ font-family: Arial, sans-serif; font-size: 16px; font-weight: bold; text-anchor: middle; }}
            .date {{ font-family: Arial, sans-serif; font-size: 14px; text-anchor: middle; }}
            .month {{ font-family: Arial, sans-serif; font-size: 18px; font-weight: bold; text-anchor: start; }}
            .day-number {{ font-family: Arial, sans-serif; font-size: 14px; text-anchor: end; }}
            .event {{ font-family: Arial, sans-serif; font-size: 10px; text-anchor: start; }}
            .event-rect {{ stroke: #666666; stroke-width: 0.5; }}
            .cell {{ fill: white; stroke: #cccccc; stroke-width: 1; }}
            .saturday {{ fill: #e3f2fd; }}
            .sunday {{ fill: #ffebee; }}
            .today {{ fill: #ffffa8; stroke: #cccccc; stroke-width: 1; }}
        </style>
    </defs>
    
    <rect width="{total_width}" height="{total_height}" fill="#fafafa"/>
'''
        
        y_offset = self.margin
        for i, day_name in enumerate(self.week_days):
            x = self.margin + i * self.cell_width
            svg_content += f'''
    <rect x="{x}" y="{y_offset}" width="{self.cell_width}" height="{self.header_height}" 
          class="cell" fill="#e0e0e0"/>
    <text x="{x + self.cell_width//2}" y="{y_offset + self.header_height//2 + 5}" 
          class="header">{day_name}</text>'''
        
        for week_idx, week in enumerate(weeks):
            y = self.margin + self.header_height + week_idx * self.cell_height
            
            for day_idx, date in enumerate(week):
                x = self.margin + day_idx * self.cell_width
                
                cell_class = "cell"
                if date == today_date:
                    cell_class += " today"
                elif day_idx == 5:
                    cell_class += " saturday"
                elif day_idx == 6:
                    cell_class += " sunday"
                
                month_text = ""
                if date.day == 1:
                    month_text = f'<text x="{x + 8}" y="{y + 20}" class="month">{date.month}月</text>'
                
                svg_content += f'''
    <rect x="{x}" y="{y}" width="{self.cell_width}" height="{self.cell_height}" 
          class="{cell_class}"/>
    {month_text}
    <text x="{x + self.cell_width - 8}" y="{y + 20}" 
          class="day-number">{date.day}</text>'''
        
        for week_idx, week in enumerate(weeks):
            y = self.margin + self.header_height + week_idx * self.cell_height
            
            drawn_events = set()
            
            for day_idx, date in enumerate(week):
                x = self.margin + day_idx * self.cell_width
                
                if date in date_event_positions:
                    events_on_date = date_event_positions[date]
                    for pos, event in enumerate(events_on_date):
                        if event is not None:
                            event_id = (event['member'], event['start_date'], event['end_date'])
                            if event_id not in drawn_events:
                                if event['start_date'] <= date <= event['end_date']:
                                    week_start = week[0]
                                    week_end = week[6]
                                    event_start_in_week = max(event['start_date'], week_start)
                                    event_end_in_week = min(event['end_date'], week_end)
                                    
                                    if event_start_in_week == date:
                                        drawn_events.add(event_id)
                                        
                                        start_day_idx = event_start_in_week.weekday()
                                        end_day_idx = event_end_in_week.weekday()
                                        event_length = end_day_idx - start_day_idx + 1
                                        
                                        event_width = event_length * self.cell_width - 4
                                        event_y = y + 30 + pos * (self.event_height + 2)
                                        member_color = self.member_colors.get(event['member'], '#f0f0f0')
                                        
                                        if event['description'].strip():
                                            display_text = f"{event['member']}: {event['description'][:15]}"
                                            if len(event['description']) > 15:
                                                display_text += "..."
                                        else:
                                            display_text = event['member']

                                        text_element = ""
                                        if display_text:
                                            text_element = f'<text x="{x + 4}" y="{event_y + 12}" class="event">{display_text}</text>'
                                        
                                        svg_content += f'''
    <rect x="{x + 2}" y="{event_y}" width="{event_width}" height="{self.event_height}" 
          fill="{member_color}" class="event-rect"/>
    {text_element}'''
        
        svg_content += '''
</svg>'''
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(svg_content)
        
        return output_file
    
    def convert_svg_to_png(self, svg_file):
        png_file = svg_file.replace('.svg', '.png')
        
        try:
            image = pyvips.Image.new_from_file(svg_file, dpi=300)
            image.write_to_file(png_file)
            print(f"PNG変換成功: {png_file}")
            return png_file
            
        except Exception as e:
            print(f"pyvips PNG変換エラー: {e}")
            return None
    
    def print_date_info(self, today=None):
        weeks, today_date = self.get_four_week_range(today)
        print(f"基準日: {today_date}")
        print(f"4週間の日付範囲:")
        
        for week_idx, week in enumerate(weeks):
            week_type = ["前週", "当週", "次週1", "次週2"][week_idx]
            print(f"  {week_type}: {week[0]} ～ {week[-1]}")

def upload_to_slack(file_path, channel_id, token):
    """生成した画像をSlackにアップロードする"""
    print(f"Slackにファイルをアップロード中: {file_path}")
    url = "https://slack.com/api/files.upload"
    
    try:
        with open(file_path, "rb") as f:
            files = {'file': f}
            data = {
                'token': token,
                'channels': channel_id
            }
            response = requests.post(url, data=data, files=files)
            
            if response.status_code == 200 and response.json().get('ok'):
                print("Slackへのアップロードに成功しました。")
                print(response.text)
            else:
                print(f"Slackへのアップロードに失敗しました。ステータスコード: {response.status_code}")
                print(response.text)
    except FileNotFoundError:
        print(f"エラー: ファイルが見つかりません。{file_path}")
    except Exception as e:
        print(f"Slackアップロード中にエラーが発生しました: {e}")


def main():
    """メイン関数"""
    
    # SlackのボットトークンとチャンネルIDを環境変数から取得する
    SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
    SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID")

    generator = CalendarSVGGenerator()
    
    # JSONファイルから予定を読み込む
    generator.load_events_from_json("vacation_data.json")
    
    if not generator.events:
        print("予定データが読み込まれませんでした。処理を終了します。")
        return

    # SVGを生成
    svg_output_file = generator.generate_svg(output_file="calendar.svg")
    print(f"カレンダーSVGを生成しました: {svg_output_file}")
    
    # PNGに変換
    png_output_file = generator.convert_svg_to_png(svg_output_file)
    
    if png_output_file:
        # 変換成功の場合、Slackに画像をアップロード
        if SLACK_BOT_TOKEN and SLACK_CHANNEL_ID:
            upload_to_slack(png_output_file, SLACK_CHANNEL_ID, SLACK_BOT_TOKEN)
        else:
            print("警告: SlackトークンまたはチャンネルIDが環境変数に設定されていません。Slackへのアップロードをスキップします。")
    
    # デバッグ情報を表示
    generator.print_date_info()
    
    print(f"\n読み込んだ予定数: {len(generator.events)}")
    print(f"メンバー数: {len(generator.member_colors)}")
    for member, color in generator.member_colors.items():
        print(f"  {member}: {color}")

if __name__ == "__main__":
    main()
