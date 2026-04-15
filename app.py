import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 1. 페이지 설정
st.set_page_config(page_title="KOSPI 200 전략 대시보드", layout="wide")
st.title("📊 KOSPI 200 커버드콜 전략 조종석")

# 2. 리밸런싱일(금요일) 계산 함수
def get_rebalance_days(date_index):
    rebalance_dates = []
    # 최신 Pandas 버전 대응 (M -> ME)
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

# 3. 데이터 로드 및 포장지 벗기기(MultiIndex 해제)
ticker_symbol = "^KS200"
df = yf.download(ticker_symbol, period="1y", progress=False)

# [핵심 수정] 데이터가 다중 구조(MultiIndex)라면 한 겹 벗겨냅니다.
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

if not df.empty:
    rebalance_days = get_rebalance_days(df.index)

    # 4. 현재 상태 요약
    last_rebalance = rebalance_days[-1]
    current_df = df.loc[df.index >= last_rebalance]
    
    # 확실하게 숫자(float)로 변환
    base_price = float(current_df['Close'].iloc[0])
    current_price = float(current_df['Close'].iloc[-1])
    target_price = base_price * 1.05
    profit_rate = ((current_price - base_price) / base_price) * 100

    col1, col2, col3 = st.columns(3)
    # 이제 current_price는 확실한 숫자이므로 아래 서식이 정상 작동합니다.
    col1.metric("현재 지수", f"{current_price:.2f}")
    col2.metric("목표 지수 (5%)", f"{target_price:.2f}", delta=f"{target_price - current_price:.2f} 남음", delta_color="inverse")
    col3.metric("현재 수익률", f"{profit_rate:.2f}%")

    # 5. 차트 시각화
    st.subheader("📈 구간별 목표 달성 현황 (최근 1년)")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name="KOSPI 200", line=dict(color='lightgray', width=1)))

    for r_day in rebalance_days:
        temp_df = df.loc[df.index >= r_day].head(22)
        if not temp_df.empty:
            b_p = float(temp_df['Close'].iloc[0])
            t_p = b_p * 1.05
            fig.add_shape(type="line", x0=temp_df.index[0], x1=temp_df.index[-1], y0=t_p, y1=t_p,
                          line=dict(color="Red", width=1, dash="dot"))
            
            hits = temp_df[temp_df['Close'] >= t_p]
            if not hits.empty:
                fig.add_trace(go.Scatter(x=hits.index, y=hits['Close'], mode='markers', 
                                         marker=dict(color='orange', symbol='triangle-up', size=8), showlegend=False))

    fig.update_layout(height=600, template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)
    st.info(f"마지막 업데이트: {df.index[-1].strftime('%Y-%m-%d')} | 기준일: {last_rebalance.strftime('%Y-%m-%d')}")
else:
    st.error("데이터를 불러오지 못했습니다.")
