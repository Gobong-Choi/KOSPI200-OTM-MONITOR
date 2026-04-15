import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# 1. 페이지 설정
st.set_page_config(page_title="KOSPI 200 전략 모니터", layout="wide")
st.title("📊 KOSPI 200 전략 모니터 (v3.0)")

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

# 데이터 정리 (Syntax Error 수정 지점)
df = df_all['Close'].copy()
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

# 배당(분배금) 데이터
dividends = etf_info.dividends
dividends.index = dividends.index.tz_localize(None)

if not df.empty:
    rebalance_days = get_rebalance_days(df.index)
    last_rebalance = rebalance_days[-1]
    current_df = df.loc[df.index >= last_rebalance]
    
    # 지표 계산
    base_price = float(current_df['^KS200'].iloc[0]) 
    current_price = float(current_df['^KS200'].iloc[-1])
    target_price = base_price * 1.05
    profit_rate = ((current_price - base_price) / base_price) * 100

    # 4. 상단 대시보드 (순서: 기준 -> 목표 -> 현재 -> 기준지수대비)
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("기준 지수", f"{base_price:.2f}", help=f"기준일: {last_rebalance.strftime('%Y-%m-%d')}")
    
    target_diff = target_price - current_price
    if target_diff <= 0:
        target_label, t_delta_color = "🔥 초과 상태 중", "normal"
    else:
        target_label, t_delta_color = f"{target_diff:.2f} 남음", "inverse"
    col2.metric("목표 지수 (5%)", f"{target_price:.2f}", delta=target_label, delta_color=t_delta_color)

    base_diff = current_price - base_price
    col3.metric("현재 지수", f"{current_price:.2f}", delta=f"{base_diff:+.2f}", delta_color="normal")
    
    col4.metric("기준지수대비", f"{profit_rate:.2f}%")

    # 5. 차트 시각화
    st.subheader("📈 지수 vs ETF 수익률 동기화 (영점 조정)")
    fig = go.Figure()
    alert_logs = []
    now = datetime.now()

    for i, r_day in enumerate(rebalance_days):
        next_r_day = rebalance_days[i+1] if i + 1 < len(rebalance_days) else df.index[-1]
        temp_df = df.loc[(df.index >= r_day) & (df.index <= next_r_day)].copy()
        
        if not temp_df.empty:
            s_idx = float(temp_df['^KS200'].iloc[0])
            s_etf = float(temp_df
