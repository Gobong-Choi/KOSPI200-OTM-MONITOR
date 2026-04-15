import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# 1. 페이지 설정
st.set_page_config(page_title="KOSPI 200 전략 모니터", layout="wide")
st.title("📊 KOSPI 200 전략 모니터 (v3.7)")

SYSTEM_START_DATE = datetime(2026, 4, 14).date()

# 텔레그램 테스트 함수
def send_telegram_test():
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("CHAT_ID")
    if not token or not chat_id:
        st.error("❌ Secrets 설정을 확인해주세요.")
        return
    msg = f"🔔 [전략 모니터] 테스트 성공!\n일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={msg}"
    try:
        res = requests.get(url)
        if res.status_code == 200: st.success("✅ 테스트 성공!")
        else: st.error(f"❌ 실패 (코드: {res.status_code})")
    except Exception as e: st.error(f"❌ 오류: {e}")

# 2. 데이터 로드 및 전처리
ticker_id = "166400.KS"
tickers = ["^KS200", ticker_id]

try:
    df_all = yf.download(tickers, period="1y", progress=False)
    # [핵심 수정] 지수 데이터의 시간대(Timezone) 정보를 강제로 제거합니다.
    if not df_all.empty:
        df_all.index = df_all.index.tz_localize(None)
    
    etf_info = yf.Ticker(ticker_id)
    df = df_all['Close'].copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # 분배금 데이터 추출 및 시간대 제거
    dividends = etf_info.dividends
    if not dividends.empty:
        dividends.index = pd.to_datetime(dividends.index).tz_localize(None).normalize()
        dividends = dividends[dividends.index >= (datetime.now() - timedelta(days=365))]
except Exception as e:
    st.error(f"데이터 로드 중 오류 발생: {e}")
    df = pd.DataFrame()
    dividends = pd.Series()

with st.sidebar:
    st.header("🛠 시스템 설정")
    if st.button("📲 텔레그램 테스트 문자 발송"): send_telegram_test()
    st.divider()
    st.subheader("📊 데이터 상태")
    st.write(f"분배금 데이터: {'✅ 로드됨' if not dividends.empty else '❌ 데이터 없음'}")

# 리밸런싱일 계산 함수
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

if not df.empty:
    rebalance_days = get_rebalance_days(df.index)
    last_rebalance = rebalance_days[-1]
    current_df = df.loc[df.index >= last_rebalance]
    
    # 지표 계산
    base_price = float(current_df['^KS200'].iloc[0]) 
    current_price = float(current_df['^KS200'].iloc[-1])
    target_price = base_price * 1.05
    profit_rate = ((current_price - base_price) / base_price) * 100

    # 3. 상단 지표 (순서: 기준 -> 목표 -> 현재 -> 기준지수대비)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("기준 지수", f"{base_price:.2f}")
    t_diff = target_price - current_price
    t_label, t_color = ("🔥 초과 상태 중", "normal") if t_diff <= 0 else (f"{t_diff:.2f} 남음", "inverse")
    col2.metric("목표 지수 (5%)", f"{target_price:.2f}", delta=t_label, delta_color=t_color)
    col3.metric("현재 지수", f"{current_price:.2f}", delta=f"{current_price - base_price:+.2f}")
    col4.metric("기준지수대비", f"{profit_rate:.2f}%")

    # 4. 차트 시각화
    st.subheader("📈 지수 vs ETF (영점 조정 및 분배락 표기)")
    fig = go.Figure()
    alert_logs = []
    now = datetime.now()

    # 범례 고정용 가짜 데이터
    fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers', marker=dict(color='green', symbol='star', size=10), name='분배락일(★)'))

    for i, r_day in enumerate(rebalance_days):
        next_r_day = rebalance_days[i+1] if i + 1 < len(rebalance_days) else df.index[-1]
        temp_df = df.loc[(df.index >= r_day) & (df.index <= next_r_day)].copy()
        
        if not temp_df.empty:
            s_idx = float(temp_df['^KS200'].iloc[0])
            s_etf = float(temp_df[ticker_id].iloc[0])
            temp_df['Adj_ETF'] = (temp_df[ticker_id] / s_etf) * s_idx
            
            # 메인 선
            fig.add_trace(go.Scatter(x=temp_df.index, y=temp_df['^KS200'], name="KOSPI 200", line=dict(color='lightgray', width=1), showlegend=(i == 0)))
            fig.add_trace(go.Scatter(x=temp_df.index, y=temp_df['Adj_ETF'], name="TIGER 커버드콜", line=dict(color='blue', width=1), showlegend=(i == 0)))
            
            # [수정] 분배락 표시 로직 (시간대 통일 후 안전하게 매칭)
            if not dividends.empty:
                seg_div = dividends[(dividends.index >= temp_df.index[0]) & (dividends.index <= temp_df.index[-1])]
                for d_date
