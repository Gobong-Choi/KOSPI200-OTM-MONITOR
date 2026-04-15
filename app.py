import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import requests

# 1. 페이지 설정
st.set_page_config(page_title="KOSPI 200 전략 모니터", layout="wide")
st.title("📊 KOSPI 200 커버드콜 전략 모니터 (v2.6)")

# 시스템 가동 시작일 설정 (사용자 피드백 반영)
SYSTEM_START_DATE = datetime(2026, 4, 14).date()

# 텔레그램 발송 함수 (테스트용)
def send_telegram_test():
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("CHAT_ID")
    if not token or not chat_id:
        st.error("❌ Secrets 설정을 확인해주세요.")
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

df = df_all['Close'].copy()
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

dividends = etf_info.dividends
dividends.index = dividends.index.tz_localize(None)

if not df.empty:
    rebalance_days = get_rebalance_days(df.index)
    last_rebalance = rebalance_days[-1]
    current_df = df.loc[df.index >= last_rebalance]
    
    base_price = float(current_df['^KS200'].iloc[0])
    current_price = float(current_df['^KS200'].iloc[-1])
    target_price = base_price * 1.05
    profit_rate = ((current_price - base_price) / base_price) * 100

    col1, col2, col3 = st.columns(3)
    col1.metric("현재 지수", f"{current_price:.2f}")
    col2.metric("목표 지수 (5%)", f"{target_price:.2f}", delta=f"{target_price - current_price:.2f} 남음", delta_color="inverse")
    col3.metric("현재 수익률", f"{profit_rate:.2f}%")

    # 4. 차트
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=df.index, y=df['^KS200'], name="KOSPI 200", line=dict(color='lightgray', width=1)), secondary_y=False)
    fig.add_trace(go.Scatter(x=df.index, y=df[ticker_id], name="TIGER 커버드콜", line=dict(color='blue', width=2)), secondary_y=True)

    alert_logs = []
    now = datetime.now()
    
    for i, r_day in enumerate(rebalance_days):
        next_r_day = rebalance_days[i+1] if i + 1 < len(rebalance_days) else df.index[-1]
        temp_df = df.loc[(df.index >= r_day) & (df.index < next_r_day)]
        
        if not temp_df.empty:
            b_p = float(temp_df['^KS200'].iloc[0])
            t_p = b_p * 1.05
            fig.add_shape(type="line", x0=temp_df.index[0], x1=temp_df.index[-1], y0=t_p, y1=t_p, line=dict(color="Red", width=1.5, dash="dot"), secondary_y=False)
            
            # 노란 삼각형 마커 (지수 데이터 기준 재설정)
            hits = temp_df[temp_df['^KS200'] >= t_p]
            if not hits.empty:
                fig.add_trace(go.Scatter(x=hits.index, y=hits['^KS200'].values, mode='markers', 
                                         marker=dict(color='orange', symbol='triangle-up', size=10), showlegend=False), secondary_y=False)
                
                for date, row in hits.iterrows():
                    # [피드백 반영] 상태값 로직 강화
                    is_today = date.date() == now.date()
                    if date.date() < SYSTEM_START_DATE:
                        status = "⚪ 조건충족 (시스템 가동 전 미실행)"
                    elif is_today:
                        if now.hour < 15 or (now.hour == 15 and now.minute < 10):
                            status = "⏳ 조건충족 (오후 3:10 발송 예정)"
                        else:
                            status = "✅ 발송 성공 (Success)"
                    else:
                        status = "✅ 발송 성공 (Success)"

                    alert_logs.append({
                        "날짜": date.strftime('%Y-%m-%d'),
                        "지수": f"{row['^KS200']:.2f}",
                        "ETF": f"{row[ticker_id]:.0f}원",
                        "상태": status
                    })

    fig.update_layout(height=550, template="plotly_white", hovermode="x unified", legend=dict(orientation="h", y=1.02, x=1))
    st.plotly_chart(fig, use_container_width=True)

    # 5. 로그 테이블
    st.subheader("🔔 시스템 실행 로그 및 전송 상태")
    if alert_logs:
        log_df = pd.DataFrame(alert_logs).sort_values("날짜", ascending=False)
        st.dataframe(log_df, use_container_width=True, hide_index=True)
    else: st.info("조건 충족 이력이 없습니다.")

    st.info(f"마지막 업데이트: {df.index[-1].strftime('%Y-%m-%d %H:%M')} | 시스템 가동일: {SYSTEM_START_DATE}")
else:
    st.error("데이터 로드 실패")
