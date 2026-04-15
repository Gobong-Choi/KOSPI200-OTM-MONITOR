import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import requests

# 1. 페이지 설정
st.set_page_config(page_title="KOSPI 200 전략 모니터", layout="wide")
st.title("📊 KOSPI 200 전략 모니터 (v3.2)")

# 시스템 가동 시작일 설정
SYSTEM_START_DATE = datetime(2026, 4, 14).date()

# 텔레그램 테스트 함수 (사이드바)
def send_telegram_test():
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("CHAT_ID")
    if not token or not chat_id:
        st.error("❌ Secrets 설정을 확인해주세요 (TELEGRAM_TOKEN, CHAT_ID)")
        return
    test_msg = f"🔔 [전략 모니터] 테스트 성공!\n일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={test_msg}"
    try:
        res = requests.get(url)
        if res.status_code == 200: st.success("✅ 테스트 메시지 발송 완료!")
        else: st.error(f"❌ 실패 (코드: {res.status_code})")
    except Exception as e: st.error(f"❌ 오류: {e}")

with st.sidebar:
    st.header("🛠 시스템 설정")
    if st.button("📲 텔레그램 테스트 문자 발송"): send_telegram_test()

# 2. 리밸런싱일 계산 함수
def get_rebalance_days(date_index):
    rebalance_dates = []
    groups = date_index.to_series().groupby(pd.Grouper(freq='ME'))
    for _, group in groups:
        if group.empty: continue
        first_day = group.iloc[0].replace(day=1)
        w = first_day.weekday() 
        first_thu = first_day + timedelta(days=((3 - w + 7) % 7))
        second_thu = first_thu + timedelta(days=7)
        friday = second_thu + timedelta(days=1)
        if friday.strftime('%Y-%m-%d') in date_index.strftime('%Y-%m-%d'):
            rebalance_dates.append(friday)
    return rebalance_dates

# 3. 데이터 로드
ticker_id = "166400.KS"
tickers = ["^KS200", ticker_id]
df_all = yf.download(tickers, period="1y", progress=False)
etf_info = yf.Ticker(ticker_id)

# 데이터 정리
df = df_all['Close'].copy()
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

# 분배금(배당) 데이터 확보
dividends = etf_info.dividends
dividends.index = dividends.index.tz_localize(None)

if not df.empty:
    rebalance_days = get_rebalance_days(df.index)
    last_rebalance = rebalance_days[-1]
    current_df = df.loc[df.index >= last_rebalance]
    
    # 지표 계산
    base_price = float(current_df['^KS2
