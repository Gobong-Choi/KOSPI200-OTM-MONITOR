import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# 1. 페이지 설정
st.set_page_config(page_title="KOSPI 200 전략 모니터", layout="wide")
st.title("📊 KOSPI 200 전략 모니터 (v3.4)")

SYSTEM_START_DATE = datetime(2026, 4, 14).date()

# 텔레그램 테스트 함수
def send_telegram_test():
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("CHAT_ID")
    if not token or not chat_id:
        st.error("❌ Secrets 설정을 확인해주세요.")
        return
    msg = f"🔔 [전략 모니터] 테스트 성공!\n일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
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

df = df_all['Close'].copy()
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

# 분배금 데이터 (날짜 형식 정규화)
dividends = etf_info.dividends
if not dividends.empty:
    dividends.index = dividends.index.tz_localize(None).normalize()

if not df.empty:
    rebalance_days = get_rebalance_days(df.index)
    last_rebalance = rebalance_days[-1]
    current_df = df.loc[df.index >= last_rebalance]
    
    base_price = float(current_df['^KS200'].iloc[0]) 
    current_price = float(current_df['^KS200'].iloc[-1])
    target_price = base_price * 1.05
    profit_rate = ((current_price - base_price) / base_price) * 100

    # 4. 상단 지표
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("기준 지수", f"{base_price:.2f}", help=f"기준일: {last_rebalance.strftime('%Y-%m-%d')}")
    t_diff = target_price - current_price
    t_label, t_color = ("🔥 초과 상태 중", "normal") if t_diff <= 0 else (f"{t_diff:.2f} 남음", "inverse")
    col2.metric("목표 지수 (5%)", f"{target_price:.2f}", delta=t_label, delta_color=t_color)
    b_diff = current_price - base_price
    col3.metric("현재 지수", f"{current_price:.2f}", delta=f"{b_diff:+.2f}", delta_color="normal")
    col4.metric("기준지수대비", f"{profit_rate:.2f}%")

    # 5. 차트 시각화
    st.subheader("📈 지수 vs ETF (영점 조정 및 분배락 강조)")
    fig = go.Figure()
    alert_logs = []
    now = datetime.now()

    # 분배락일 마킹용 리스트
    div_x, div_y = [], []

    for i, r_day in enumerate(rebalance_days):
        next_r_day = rebalance_days[i+1] if i + 1 < len(rebalance_days) else df.index[-1]
        temp_df = df.loc[(df.index >= r_day) & (df.index <= next_r_day)].copy()
        
        if not temp_df.empty:
            s_idx = float(temp_df['^KS200'].iloc[0])
            s_etf = float(temp_df[ticker_id].iloc[0])
            temp_df['Adj_ETF'] = (temp_df[ticker_id] / s_etf) * s_idx
            
            # 그래프 선
            fig.add_trace(go.Scatter(x=temp_df.index, y=temp_df['^KS200'], name="KOSPI 200", line=dict(color='lightgray', width=1), showlegend=(i == 0)))
            fig.add_trace(go.Scatter(x=temp_df.index, y=temp_df['Adj_ETF'], name="TIGER 커버드콜", line=dict(color='blue', width=1), showlegend=(i == 0)))
            
            # [수정] 분배락일 시인성 강화 (세로선 + 별표 마커)
            d_in_range = dividends[(dividends.index >= temp_df.index[0]) & (dividends.index <= temp_df.index[-1])]
            for d_date, _ in d_in_range.items():
                # 세로선 두께와 선명도 증가
                fig.add_vline(x=d_date, line_width=1.5, line_dash="dot", line_color="rgba(0,128,0,0.6)")
                # ETF 선 위에 별표 찍기 위해 좌표 저장
                if d_date in temp_df.index:
                    div_x.append(d_date)
                    div_y.append(temp_df.loc[d_date, 'Adj_ETF'])
            
            # 목표선
            t_p = s_idx * 1.05
            fig.add_shape(type="line", x0=temp_df.index[0], x1=temp_df.index[-1], y0=t_p, y1=t_p, line=dict(color="Red", width=1.2, dash="dot"))
            
            # 노란 삼각형
            hits = temp_df[temp_df['^KS200'] >= t_p]
            if not hits.empty:
                fig.add_trace(go.Scatter(x=hits.index, y=hits['^KS200'].values, mode='markers', marker=dict(color='orange', symbol='triangle-up', size=10), showlegend=False))
                for date, row in hits.iterrows():
                    is_today = date.date() == now.date()
                    if date.date() < SYSTEM_START_DATE: status = "⚪ 조건충족 (시스템 가동 전 미실행)"
                    elif is_today and (now.hour < 15 or (now.hour == 15 and now.minute < 10)): status = "⏳ 조건충족 (오후 3:10 발송 예정)"
                    else: status = "✅ 발송 성공 (Success)"
                    alert_logs.append({"날짜": date.strftime('%Y-%m-%d'), "지수": f"{row['^KS200']:.2f}", "상태": status})

    # [신규] 분배락 지점에 초록색 별표 마커 추가
    if div_x:
        fig.add_trace(go.Scatter(x=div_x, y=div_y, mode='markers', name="분배락일",
                                 marker=dict(color='green', size=10, symbol='star'), showlegend=True))

    fig.update_layout(height=550, template="plotly_white", hovermode="x unified", legend=dict(orientation="h", y=1.02, x=1))
    st.plotly_chart(fig, use_container_width=True)

    # 6. 하단 정보
    l_col, d_col = st.columns(2)
    with l_col:
        st.subheader("🔔 시스템 실행 로그")
        if alert_logs: st.dataframe(pd.DataFrame(alert_logs).sort_values("날짜", ascending=False), use_container_width=True, hide_index=True)
        else: st.info("조건 충족 이력이 없습니다.")
    with d_col:
        st.subheader("💰 최근 분배금 이력")
        if not dividends.empty:
            d_df = dividends.reset_index()
            d_df.columns = ['배당락일', '분배금(원)']
            st.dataframe(d_df.sort_values('배당락일', ascending=False).head(12), use_container_width=True, hide_index=True)

    st.info(f"마지막 업데이트: {df.index[-1].strftime('%Y-%m-%d %H:%M')}")
else:
    st.error("데이터 로드 실패")
