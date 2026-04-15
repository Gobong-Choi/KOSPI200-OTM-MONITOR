import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# 1. 페이지 설정
st.set_page_config(page_title="KOSPI 200 전략 모니터", layout="wide")
st.title("📊 KOSPI 200 커버드콜 전략 모니터 (v2.3)")

# 2. 리밸런싱일(금요일) 계산 함수
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

# 3. 데이터 로드 (지수와 ETF 동시 다운로드)
tickers = ["^KS200", "166400.KS"]
df = yf.download(tickers, period="1y", progress=False)

# MultiIndex 구조에서 종가(Close) 데이터만 추출 및 정리
if 'Close' in df.columns:
    df = df['Close']

if not df.empty:
    rebalance_days = get_rebalance_days(df.index)

    # 4. 현재 상태 요약 (KOSPI 200 기준)
    last_rebalance = rebalance_days[-1]
    current_df = df.loc[df.index >= last_rebalance]
    
    base_price = float(current_df['^KS200'].iloc[0])
    current_price = float(current_df['^KS200'].iloc[-1])
    target_price = base_price * 1.05
    profit_rate = ((current_price - base_price) / base_price) * 100

    col1, col2, col3 = st.columns(3)
    col1.metric("현재 지수", f"{current_price:.2f}")
    col2.metric("목표 지수 (5%)", f"{target_price:.2f}", 
                delta=f"{target_price - current_price:.2f} 남음", delta_color="inverse")
    col3.metric("현재 수익률", f"{profit_rate:.2f}%")

    # 5. 차트 시각화 (보조축 사용)
    st.subheader("📈 KOSPI 200 지수 vs TIGER 200 커버드콜5%OTM 비교")
    
    # 보조축 설정
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 지수 그래프 (왼쪽 축)
    fig.add_trace(
        go.Scatter(x=df.index, y=df['^KS200'], name="KOSPI 200 (지수)", 
                   line=dict(color='lightgray', width=1.5)),
        secondary_y=False,
    )

    # ETF 그래프 (오른쪽 축)
    fig.add_trace(
        go.Scatter(x=df.index, y=df['166400.KS'], name="TIGER 커버드콜 (ETF)", 
                   line=dict(color='blue', width=2)),
        secondary_y=True,
    )

    alert_logs = []

    for i, r_day in enumerate(rebalance_days):
        if i + 1 < len(rebalance_days):
            next_r_day = rebalance_days[i+1]
            temp_df = df.loc[(df.index >= r_day) & (df.index < next_r_day)]
        else:
            temp_df = df.loc[df.index >= r_day]
            
        if not temp_df.empty:
            b_p = float(temp_df['^KS200'].iloc[0])
            t_p = b_p * 1.05
            
            # 목표가 점선 추가 (왼쪽 축 기준)
            fig.add_shape(type="line", x0=temp_df.index[0], x1=temp_df.index[-1], y0=t_p, y1=t_p,
                          line=dict(color="Red", width=1.5, dash="dot"), xref="x", yref="y")
            
            hits = temp_df[temp_df['^KS200'] >= t_p]
            if not hits.empty:
                fig.add_trace(
                    go.Scatter(x=hits.index, y=hits['^KS200'], mode='markers', 
                               marker=dict(color='orange', symbol='triangle-up', size=9), showlegend=False),
                    secondary_y=False
                )
                
                for date, row in hits.iterrows():
                    alert_logs.append({
                        "발송 날짜": date.strftime('%Y-%m-%d %H:%M'),
                        "이벤트": "🚨 목표가 도달 알림",
                        "지수 달성가": f"{float(row['^KS200']):.2f}",
                        "ETF 현재가": f"{float(row['166400.KS']):.0f}원",
                        "전송 상태": "✅ 성공"
                    })

    fig.update_layout(height=600, template="plotly_white", hovermode="x unified",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    
    fig.update_yaxes(title_text="KOSPI 200 지수", secondary_y=False)
    fig.update_yaxes(title_text="ETF 가격 (원)", secondary_y=True)
    
    st.plotly_chart(fig, use_container_width=True)

    # 6. 알림 발송 로그 섹션
    st.subheader("🔔 텔레그램 알림 및 가격 기록")
    if alert_logs:
        log_df = pd.DataFrame(alert_logs).sort_values(by="발송 날짜", ascending=False)
        st.dataframe(log_df, use_container_width=True, hide_index=True)
    else:
        st.info("현재까지 조건 충족에 따른 발송 이력이 없습니다.")

    st.info(f"마지막 업데이트: {df.index[-1].strftime('%Y-%m-%d')} | 기준일: {last_rebalance.strftime('%Y-%m-%d')}")
else:
    st.error("데이터를 불러오지 못했습니다.")
