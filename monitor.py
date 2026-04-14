import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime, timedelta

def send_telegram(msg):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("CHAT_ID")
    if not token or not chat_id:
        print("토큰 또는 채팅 ID가 설정되지 않았습니다.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={msg}"
    requests.get(url)

def get_rebalance_date():
    now = datetime.now()
    first_day = now.replace(day=1)
    w = first_day.weekday() 
    first_thu = first_day + timedelta(days=((3 - w + 7) % 7))
    second_thu = first_thu + timedelta(days=7)
    return second_thu + timedelta(days=1) # 금요일

# 1. 지수 데이터 확인 (최신 데이터 1건만 확실하게 가져오기)
ticker = "^KS200"
df = yf.download(ticker, period="5d", progress=False)

if not df.empty:
    # .values[-1]를 사용해 표 형식이 아닌 순수 숫자값만 추출합니다.
    current_price = float(df['Close'].values[-1])
    
    # 2. 이번 달 리밸런싱 기준일(금요일) 데이터 확인
    rebalance_date = get_rebalance_date()
    target_df = yf.download(ticker, 
                            start=rebalance_date.strftime('%Y-%m-%d'), 
                            end=(rebalance_date + timedelta(days=3)).strftime('%Y-%m-%d'),
                            progress=False)

    if not target_df.empty:
        # 첫 번째 행의 종가를 숫자로 변환
        base_price = float(target_df['Close'].values[0])
        target_price = base_price * 1.05
        
        print(f"현재가: {current_price}, 기준가: {base_price}, 목표가: {target_price}")
        
        # 이제 숫자 vs 숫자 비교이므로 에러가 나지 않습니다.
        if current_price >= target_price:
            send_telegram(f"🚨 [KOSPI 200] 목표가 도달!\n기준가(금): {base_price:.2f}\n현재가: {current_price:.2f}")
        else:
            print("아직 목표가에 도달하지 않았습니다.")
    else:
        print("이번 달 리밸런싱일 데이터를 찾을 수 없습니다.")
else:
    print("현재 지수 데이터를 가져오지 못했습니다.")
