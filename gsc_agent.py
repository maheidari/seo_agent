import os
import json
import re
import pandas as pd
from groq import Groq
from dotenv import load_dotenv
import datetime

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ============================================================
# ابزارها
# ============================================================

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_keyword_summary",
            "description": "خلاصه کلی داده‌های GSC - اول این رو صدا بزن",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_quick_win_keywords",
            "description": "کلمات رنک 4-15 که با کمی بهبود میان صفحه اول",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_position": {"type": "number"},
                    "max_position": {"type": "number"},
                    "min_impressions": {"type": "number"}
                },
                "required": ["min_position", "max_position"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_low_ctr_keywords",
            "description": "کلمات با impression بالا ولی CTR پایین - مشکل title یا meta",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_impressions": {"type": "number"},
                    "max_ctr": {"type": "number"}
                },
                "required": ["min_impressions", "max_ctr"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_growth_pages",
            "description": "صفحاتی که impression بالا دارن ولی رنک هنوز 11-30 هست",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_impressions": {"type": "number"},
                    "min_position": {"type": "number"},
                    "max_position": {"type": "number"}
                },
                "required": ["min_impressions"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_content_update_opportunities",
            "description": "صفحاتی که رنک خوب دارن ولی CTR پایینه - نیاز به آپدیت محتوا",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_position": {"type": "number"},
                    "max_ctr": {"type": "number"},
                    "min_impressions": {"type": "number"}
                },
                "required": ["max_position", "max_ctr"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_keyword_gaps",
            "description": "کلماتی که impression دارن ولی کلیک صفر یا خیلی کمه - نیاز به صفحه جدید",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_impressions": {"type": "number"},
                    "max_clicks": {"type": "number"}
                },
                "required": ["min_impressions"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_cannibalization",
            "description": "کلماتی که چند URL برای یه کلمه رقابت میکنن",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_impressions": {"type": "number"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_pages",
            "description": "بهترین صفحات بر اساس کلیک",
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {"type": "number"}
                },
                "required": ["top_n"]
            }
        }
    }
]


# ============================================================
# لود داده GSC
# ============================================================

def load_gsc_data(filepath):
    df = pd.read_csv(filepath)
    df.columns = df.columns.str.strip().str.lower()

    col_map = {
        'query': ['query', 'queries', 'keyword', 'top queries'],
        'clicks': ['clicks'],
        'impressions': ['impressions'],
        'ctr': ['ctr'],
        'position': ['position', 'average position']
    }

    renamed = {}
    for standard, variants in col_map.items():
        for v in variants:
            if v in df.columns:
                renamed[v] = standard
                break

    df = df.rename(columns=renamed)

    if 'ctr' in df.columns:
        df['ctr'] = df['ctr'].astype(str).str.replace('%', '').astype(float)
        if df['ctr'].max() > 1:
            df['ctr'] = df['ctr'] / 100

    for col in ['clicks', 'impressions', 'position']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    return df


# ============================================================
# پیاده‌سازی ابزارها
# ============================================================

def get_keyword_summary(df):
    top_keyword = None
    if len(df) > 0 and 'clicks' in df.columns:
        top_keyword = df.sort_values('clicks', ascending=False).iloc[0]['query']

    return {
        "total_keywords": len(df),
        "total_clicks": int(df['clicks'].sum()),
        "total_impressions": int(df['impressions'].sum()),
        "avg_ctr_percent": round(float(df['ctr'].mean()) * 100, 2),
        "avg_position": round(float(df['position'].mean()), 1),
        "keywords_top3": len(df[df['position'] <= 3]),
        "keywords_page1": len(df[(df['position'] > 3) & (df['position'] <= 10)]),
        "keywords_page2": len(df[(df['position'] > 10) & (df['position'] <= 20)]),
        "keywords_beyond_page2": len(df[df['position'] > 20]),
        "top_keyword_by_clicks": top_keyword
    }


def get_quick_win_keywords(df, min_position=4, max_position=15, min_impressions=50):
    result = df[
        (df['position'] >= min_position) &
        (df['position'] <= max_position) &
        (df['impressions'] >= min_impressions)
    ].sort_values('impressions', ascending=False)

    records = result[['query', 'clicks', 'impressions', 'ctr', 'position']].head(15).copy()
    records['ctr_percent'] = (records['ctr'] * 100).round(2)
    records['position'] = records['position'].round(1)
    records = records.drop('ctr', axis=1)

    return {
        "count": len(records),
        "description": "این کلمات رنک 4-15 دارن، با بهبود محتوا میتونن بیان صفحه اول",
        "keywords": records.to_dict('records')
    }


def get_low_ctr_keywords(df, min_impressions=100, max_ctr=0.03):
    result = df[
        (df['impressions'] >= min_impressions) &
        (df['ctr'] <= max_ctr)
    ].sort_values('impressions', ascending=False)

    records = result[['query', 'clicks', 'impressions', 'ctr', 'position']].head(15).copy()
    records['ctr_percent'] = (records['ctr'] * 100).round(2)
    records['position'] = records['position'].round(1)
    records = records.drop('ctr', axis=1)

    return {
        "count": len(records),
        "description": "این کلمات دیده میشن ولی کلیک نمیگیرن - title و meta نیاز به بهبود داره",
        "keywords": records.to_dict('records')
    }


def get_growth_pages(df, min_impressions=200, min_position=11, max_position=30):
    result = df[
        (df['impressions'] >= min_impressions) &
        (df['position'] >= min_position) &
        (df['position'] <= max_position)
    ].sort_values('impressions', ascending=False)

    if 'page' in df.columns:
        page_data = result.groupby('page').agg({
            'impressions': 'sum',
            'clicks': 'sum',
            'position': 'mean'
        }).sort_values('impressions', ascending=False).head(10)
        records = page_data.reset_index()
        records['position'] = records['position'].round(1)
        records = records.rename(columns={'page': 'url'})
        return {
            "count": len(records),
            "description": "این صفحات پتانسیل رشد بالایی دارن",
            "pages": records.to_dict('records')
        }
    else:
        records = result[['query', 'clicks', 'impressions', 'position']].head(15).copy()
        records['position'] = records['position'].round(1)
        return {
            "count": len(records),
            "description": "کلماتی که پتانسیل رشد دارن ولی هنوز صفحه اول نیستن",
            "keywords": records.to_dict('records')
        }


def get_content_update_opportunities(df, max_position=10, max_ctr=0.05, min_impressions=100):
    result = df[
        (df['position'] <= max_position) &
        (df['ctr'] <= max_ctr) &
        (df['impressions'] >= min_impressions)
    ].sort_values('impressions', ascending=False)

    records = result[['query', 'clicks', 'impressions', 'ctr', 'position']].head(15).copy()
    records['ctr_percent'] = (records['ctr'] * 100).round(2)
    records['position'] = records['position'].round(1)
    records = records.drop('ctr', axis=1)

    return {
        "count": len(records),
        "description": "این صفحات رنک خوب دارن ولی CTR پایینه - محتوا نیاز به آپدیت داره",
        "keywords": records.to_dict('records')
    }


def get_keyword_gaps(df, min_impressions=100, max_clicks=2):
    result = df[
        (df['impressions'] >= min_impressions) &
        (df['clicks'] <= max_clicks)
    ].sort_values('impressions', ascending=False)

    records = result[['query', 'clicks', 'impressions', 'ctr', 'position']].head(15).copy()
    records['ctr_percent'] = (records['ctr'] * 100).round(2)
    records['position'] = records['position'].round(1)
    records = records.drop('ctr', axis=1)

    return {
        "count": len(records),
        "description": "این کلمات دیده میشن ولی کلیک ندارن - احتمالاً صفحه مناسب ندارن",
        "keywords": records.to_dict('records')
    }


def get_cannibalization(df, min_impressions=50):
    if 'page' not in df.columns:
        return {"message": "برای کانیبالیزیشن نیاز به داده صفحات داری - فایل Pages رو از GSC export کن"}

    result = df[df['impressions'] >= min_impressions]
    keyword_pages = result.groupby('query')['page'].nunique()
    cannibalized = keyword_pages[keyword_pages > 1].index

    if len(cannibalized) == 0:
        return {"message": "کانیبالیزیشن مشخصی پیدا نشد", "count": 0}

    issues = []
    for keyword in cannibalized[:10]:
        pages = result[result['query'] == keyword][['page', 'clicks', 'impressions', 'position']]
        issues.append({
            "keyword": keyword,
            "competing_pages": pages.to_dict('records')
        })

    return {
        "count": len(cannibalized),
        "description": "این کلمات چند صفحه رقیب دارن - باید canonical یا merge بشن",
        "issues": issues
    }


def get_top_pages(df, top_n=10):
    if 'page' in df.columns:
        result = df.groupby('page').agg({
            'clicks': 'sum',
            'impressions': 'sum',
            'position': 'mean'
        }).sort_values('clicks', ascending=False).head(int(top_n))
        records = result.reset_index()
        records['position'] = records['position'].round(1)
        records = records.rename(columns={'page': 'url'})
        return {"count": len(records), "pages": records.to_dict('records')}
    else:
        result = df.sort_values('clicks', ascending=False).head(int(top_n))
        return {
            "count": len(result),
            "keywords": result[['query', 'clicks', 'impressions', 'position']].to_dict('records')
        }


def execute_tool(tool_name, tool_input, df):
    tools_map = {
        "get_keyword_summary": lambda: get_keyword_summary(df),
        "get_quick_win_keywords": lambda: get_quick_win_keywords(df, **tool_input),
        "get_low_ctr_keywords": lambda: get_low_ctr_keywords(df, **tool_input),
        "get_growth_pages": lambda: get_growth_pages(df, **tool_input),
        "get_content_update_opportunities": lambda: get_content_update_opportunities(df, **tool_input),
        "get_keyword_gaps": lambda: get_keyword_gaps(df, **tool_input),
        "get_cannibalization": lambda: get_cannibalization(df, **tool_input),
        "get_top_pages": lambda: get_top_pages(df, **tool_input),
    }
    return tools_map[tool_name]()


# ============================================================
# تبدیل به HTML
# ============================================================

def markdown_to_html(text):
    # تبدیل --- به خط جداکننده
    text = re.sub(r'^\s*---\s*$', '<hr>', text, flags=re.MULTILINE)

    def convert_table(match):
        lines = match.group(0).strip().split('\n')
        html = '<table>\n'
        first_row = True
        for line in lines:
            if re.match(r'^\|[-| :]+\|$', line.strip()):
                continue
            cells = [c.strip() for c in line.split('|') if c.strip()]
            if not cells:
                continue
            if first_row:
                html += '<tr>' + ''.join(f'<th>{c}</th>' for c in cells) + '</tr>\n'
                first_row = False
            else:
                html += '<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>\n'
        html += '</table>'
        return html

    text = re.sub(r'(\|.+\|\n)+', convert_table, text)
    text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'^> (.+)$', r'<blockquote>\1</blockquote>', text, flags=re.MULTILINE)
    text = re.sub(r'^[-•*] (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\. (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
    text = re.sub(r'(<li>.*?</li>\n?)+', lambda m: f'<ul>{m.group(0)}</ul>', text, flags=re.DOTALL)

    paragraphs = text.split('\n\n')
    result = []
    for p in paragraphs:
        p = p.strip()
        if p and not re.match(r'^<[h1-6|table|ul|blockquote]', p):
            p = f'<p>{p}</p>'
        result.append(p)

    return '\n'.join(result)


def build_chart_html(chart_data):
    """یه چارت ساده با Chart.js برای top keywords می‌سازه"""
    if not chart_data.get('quick_wins'):
        return ""

    keywords = chart_data['quick_wins'][:10]
    labels = json.dumps([k['query'] for k in keywords], ensure_ascii=False)
    impressions = json.dumps([k['impressions'] for k in keywords])
    clicks = json.dumps([k['clicks'] for k in keywords])

    return f"""
<h2>📊 نمودار کلمات کلیدی برتر</h2>
<div style="background:#f8faff; border-radius:12px; padding:20px; margin:20px 0;">
  <canvas id="kw_chart" height="100"></canvas>
</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
(function() {{
  var ctx = document.getElementById('kw_chart').getContext('2d');
  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: {labels},
      datasets: [
        {{
          label: 'ایمپرشن',
          data: {impressions},
          backgroundColor: 'rgba(26,115,232,0.7)',
          borderRadius: 6
        }},
        {{
          label: 'کلیک',
          data: {clicks},
          backgroundColor: 'rgba(52,168,83,0.7)',
          borderRadius: 6
        }}
      ]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ position: 'top' }},
        title: {{ display: false }}
      }},
      scales: {{
        x: {{ ticks: {{ font: {{ family: 'Tahoma' }} }} }},
        y: {{ beginAtZero: true }}
      }}
    }}
  }});
}})();
</script>"""


def save_html_report(content, website_url, output_path="gsc_report.html", chart_data=None, date_range=""):
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    body = markdown_to_html(content)
    chart_html = build_chart_html(chart_data or {})
    date_range_line = f"<p>📆 بازه داده: {date_range}</p>" if date_range else ""

    html = f"""<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
<meta charset="UTF-8">
<title>گزارش سئو — {website_url}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Tahoma, Arial, sans-serif; background: #f0f4f8; color: #333; padding: 30px; }}
  .container {{ max-width: 960px; margin: auto; background: white; border-radius: 16px; padding: 40px; box-shadow: 0 4px 24px rgba(0,0,0,0.1); }}
  .header {{ background: linear-gradient(135deg, #1a73e8, #0d47a1); color: white; padding: 30px; border-radius: 12px; margin-bottom: 35px; }}
  .header h1 {{ font-size: 24px; margin-bottom: 10px; }}
  .header p {{ opacity: 0.85; font-size: 14px; margin-top: 5px; }}
  h2 {{ color: #1a73e8; margin: 30px 0 15px; font-size: 20px; border-right: 4px solid #1a73e8; padding-right: 10px; }}
  h3 {{ color: #333; margin: 20px 0 10px; font-size: 17px; }}
  p {{ line-height: 1.8; margin-bottom: 12px; color: #444; }}
  hr {{ border: none; border-top: 1px solid #e8edf2; margin: 30px 0; }}
  table {{ width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 14px; }}
  th {{ background: #1a73e8; color: white; padding: 12px 10px; text-align: right; }}
  td {{ padding: 10px; border-bottom: 1px solid #eee; vertical-align: top; }}
  tr:hover td {{ background: #f0f7ff; }}
  ul {{ padding-right: 20px; margin: 10px 0; }}
  li {{ line-height: 2; color: #444; }}
  blockquote {{ background: #fff8e1; border-right: 4px solid #ffc107; padding: 15px 20px; margin: 15px 0; border-radius: 6px; color: #555; }}
  strong {{ color: #1557b0; }}
  .footer {{ text-align: center; margin-top: 40px; color: #aaa; font-size: 13px; border-top: 1px solid #eee; padding-top: 20px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📊 گزارش تحلیل سئو</h1>
    <p>🌐 سایت: {website_url}</p>
    <p>📅 تاریخ تهیه گزارش: {now}</p>
    {date_range_line}
  </div>
  {chart_html}
  {body}
  <div class="footer">این گزارش توسط SEO Agent تهیه شده است</div>
</div>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n✅ گزارش HTML ذخیره شد: {output_path}")
    return output_path


# ============================================================
# Agent اصلی
# ============================================================

def run_gsc_agent(csv_filepath, website_url="", output_path="gsc_report.html"):
    print(f"\n🤖 Agent شروع به آنالیز داده‌های GSC کرد...\n")

    df = load_gsc_data(csv_filepath)
    print(f"✅ {len(df)} کلمه کلیدی لود شد\n")

    # تشخیص بازه زمانی از ستون‌های تاریخ (اگه وجود داشت)
    date_range = ""
    for col in df.columns:
        if 'date' in col.lower():
            try:
                dates = pd.to_datetime(df[col], errors='coerce').dropna()
                if len(dates) > 0:
                    date_range = f"{dates.min().strftime('%Y-%m-%d')} تا {dates.max().strftime('%Y-%m-%d')}"
            except:
                pass

    # جمع‌آوری داده چارت در حین اجرا
    chart_data = {}

    messages = [
        {
            "role": "system",
            "content": """You are a professional SEO Agent. Analyze GSC data using ALL available tools:
1. get_keyword_summary
2. get_quick_win_keywords (min_position=4, max_position=15, min_impressions=50)
3. get_low_ctr_keywords (min_impressions=100, max_ctr=0.03)
4. get_growth_pages (min_impressions=200)
5. get_content_update_opportunities (max_position=10, max_ctr=0.05, min_impressions=100)
6. get_keyword_gaps (min_impressions=100, max_clicks=2)
7. get_cannibalization
8. get_top_pages (top_n=10)

After collecting all data, write a comprehensive report in Persian with these sections:
## خلاصه وضعیت
## فرصت‌های سریع (Quick Wins)
## صفحات با پتانسیل رشد
## فرصت‌های محتوای جدید (Keyword Gaps)
## مشکلات فنی
## برنامه اقدام (Action Plan)

IMPORTANT RULES:
- If a tool returns a "message" field indicating missing data (like cannibalization without page data), skip that section entirely — do NOT mention it in the report.
- For each keyword write exact actionable steps.
- Separate sections with ---"""
        },
        {
            "role": "user",
            "content": f"سایت: {website_url}\nداده‌های GSC رو کامل آنالیز کن"
        }
    ]

    final_content = ""

    while True:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=4000
        )

        message = response.choices[0].message

        if response.choices[0].finish_reason == "stop":
            final_content = message.content
            print("\n" + "="*60)
            print("📊 گزارش آماده شد")
            print("="*60)
            break

        if response.choices[0].finish_reason == "tool_calls":
            messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in message.tool_calls
                ]
            })

            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tool_input = json.loads(tool_call.function.arguments)
                print(f"🔧 Agent داره از '{tool_name}' استفاده میکنه...")
                result = execute_tool(tool_name, tool_input, df)

                # جمع‌آوری داده برای چارت
                if tool_name == 'get_quick_win_keywords' and 'keywords' in result:
                    chart_data['quick_wins'] = result['keywords'][:10]
                if tool_name == 'get_keyword_summary':
                    chart_data['summary'] = result

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False)
                })

    save_html_report(final_content, website_url, output_path=output_path, chart_data=chart_data, date_range=date_range)
    return final_content


# ============================================================
# اجرا
# ============================================================

if __name__ == "__main__":
    print("="*60)
    print("🔍 SEO Agent — آنالیز Google Search Console")
    print("="*60)
    csv_file = input("\nآدرس فایل CSV رو وارد کن: ")
    site_url = input("آدرس سایت (اختیاری): ")
    run_gsc_agent(csv_file, site_url)
