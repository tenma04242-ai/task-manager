import feedparser
import yfinance as yf
from google import genai
import urllib.request
import json
import os
from datetime import datetime, timezone, timedelta

# 環境変数から取得
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]

JST = timezone(timedelta(hours=9))
today = datetime.now(JST).strftime("%Y/%m/%d")

# Gemini 設定
client = genai.Client(api_key=GEMINI_API_KEY)

# RSS フィード
RSS_FEEDS = [
    ("NHK経済", "https://www.nhk.or.jp/rss/news/cat6.xml"),
    ("Yahooビジネス", "https://news.yahoo.co.jp/rss/categories/business.xml"),
]

# ニュース記事取得
articles = []
for source, url in RSS_FEEDS:
    feed = feedparser.parse(url)
    for entry in feed.entries[:6]:
        articles.append({
            "source": source,
            "title": entry.title,
            "summary": getattr(entry, "summary", "")[:200],
        })

# 株価・為替データ取得
tickers = {
    "日経平均": "^N225",
    "NYダウ": "^DJI",
    "ナスダック": "^IXIC",
    "ドル円": "USDJPY=X",
    "ユーロ円": "EURJPY=X",
}

market_data = {}
for name, symbol in tickers.items():
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="2d")
        if len(hist) >= 2:
            current = hist["Close"].iloc[-1]
            prev = hist["Close"].iloc[-2]
            change = current - prev
            pct = (change / prev) * 100
            arrow = "↑" if change >= 0 else "↓"
            market_data[name] = {
                "current": current,
                "change": change,
                "pct": pct,
                "arrow": arrow,
            }
    except Exception as e:
        print(f"{name} データ取得失敗: {e}")

# Gemini に渡すデータを整形
articles_text = "\n".join(
    [f"[{a['source']}] {a['title']} / {a['summary']}" for a in articles[:10]]
)

market_text = "\n".join([
    f"{name}: {d['current']:.2f} (前日比 {d['arrow']}{abs(d['change']):.2f} / {d['arrow']}{abs(d['pct']):.2f}%)"
    for name, d in market_data.items()
])

# Gemini でレポート生成
prompt = f"""
あなたは経済アナリストです。以下のニュース記事と市場データをもとに、日本語で経済レポートを作成してください。
出力はすべて日本語で、Slackのmarkdown形式で記述してください。英語は使用しないこと。

【本日のニュース記事】
{articles_text}

【本日の市場データ】
{market_text}

以下のフォーマットで出力してください：

💡 *今日のポイント*
・（市場全体を一言で表すサマリー）
・（最も重要なニュースを1行で）
・（投資家が特に注目すべき点を1行で）

🌏 *世界・日本経済*
• [ニュース1のタイトル]
  📊 概要：（事実・数値を簡潔に）
  🔍 背景：（なぜ起きたか・原因）
  👀 注目：（今後の影響・見どころ）

• [ニュース2のタイトル]
  📊 概要：
  🔍 背景：
  👀 注目：

• [ニュース3のタイトル]
  📊 概要：
  🔍 背景：
  👀 注目：

📈 *株式市場*
• 日経平均：（市場データの値をそのまま記載）
  📌 背景：（変動した主な理由を2〜3文で）
  👀 注目：（今後注視すべきポイント）

• NYダウ：（市場データの値をそのまま記載）
  📌 背景：
  👀 注目：

• ナスダック：（市場データの値をそのまま記載）
  📌 背景：
  👀 注目：

💱 *為替*
• ドル円：（市場データの値をそのまま記載）
  📌 背景：（変動の主な理由）
  👀 注目：（今後の動向）

• ユーロ円：（市場データの値をそのまま記載）
  📌 背景：
  👀 注目：

📅 *今週の注目イベント*
・（経済指標の発表・中央銀行イベント・重要会議など）
・（同上）
・（同上）
"""

response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents=prompt,
)
report = response.text

# Slack 投稿
message = f"📰 *今日の経済ニュース | {today}*\n\n{report}"
data = json.dumps({"text": message}).encode("utf-8")
req = urllib.request.Request(
    SLACK_WEBHOOK_URL,
    data=data,
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as r:
    print(f"投稿完了: {r.status}")
