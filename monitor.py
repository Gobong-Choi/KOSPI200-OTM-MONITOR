import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime, timedelta

def send_telegram(msg):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={msg}"
    requests.get(url)

def get_rebalance_date():
    now = datetime.now()
    first_day = now.replace(day=1)
    w = first_day.weekday() # 0(월)~6(일)
    # 2번째 목요일 계산 후 +1일(금요일)
    first_thu = first_day + timedelta(days=((3 - w + 7) % 7))
    second_thu = first_thu + timedelta(days=7)
    return second_thu + timedelta(days=1)

# 지수 데이터 확인
ticker = "^KS200"
df = yf.download(ticker, period="5d")
current_price = df['Close'].iloc[-1]

# 기준일(금요일) 종가 확인
rebalance_date = get_rebalance_date()
target_df = yf.download(ticker, start=rebalance_date.strftime('%Y-%m-%d'), end=(rebalance_date + timedelta(days=1)).strftime('%Y-%m-%d'))

if not target_df.empty:
    base_price = target_df['Close'].iloc[0]
    target_price = base_price * 1.05
    
    if current_price >= target_price:
        send_telegram(f"🚨 [자동알림] KOSPI 200 목표가 도달!\n기준가(금): {base_price:.2f}\n현재가: {current_price:.2f}")
