import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import pytz

# 1. 페이지 설정 및 제목
st.set_page_config(page_title="KOSPI 200 전략 모니터", layout="wide")
st.title("📊 KOSPI 200 전략 모니터 (v5.0 Master)")

# KST 시간대 정의 (대표님께서 제안하신 '꼬리표' 통일)
KST = pytz.timezone('Asia/Seoul')
SYSTEM_START_DATE = datetime(2026, 4, 14).date()

# 텔레그램 테스트 함수
def send_telegram_test():
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("CHAT_ID")
    if not token or not chat_id:
        st.error("❌ Secrets 설정을 확인해주세요.")
        return
    now_str = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
    msg = f"🔔 [전략 모니터] 테스트 성공!\n일시: {now_str}"
    url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={msg}"
    try:
        res = requests.get(url)
        if res.status_code == 200: st.success("✅ 텔레그램 발송 성공!")
        else: st.error(f"❌ 발송 실패 (코드: {res.status_code})")
    except Exception as e: st.error(f"❌ 오류 발생: {e}")

with st.sidebar:
    st.header("🛠 시스템 설정")
    if st.button("📲 텔레그램 테스트 문자 발송"):
        send_telegram_test()

# 2. 데이터 로드 및 '꼬리표(KST)' 통일 작업
@st.cache_data(ttl=3600)
def load_data_v5():
    ticker_id = "166400.KS"
    tickers = ["^KS200", ticker_id]
    
    # 데이터 다운로드
    raw = yf.download(tickers, period="1y", progress=False)
    
    # 모든 데이터의 시간대를 KST로 통일 (꼬리표 붙이기)
    if raw.index.tz is None:
        raw.index = raw.index.tz_localize('UTC').tz_convert(KST)
    else:
        raw.index = raw.index.tz_convert(KST)
        
    close_df = raw['Close'].copy()
    if isinstance(close_df.columns, pd.MultiIndex):
        close_df.columns = close_df.columns.get_level_values(0)
    
    # 분배금 데이터 로드 및 꼬리표 통일
    etf = yf.Ticker(ticker_id)
    divs = etf.dividends
    if not divs.empty:
        if divs.index.tz is None:
            divs.index = divs.index.tz_localize('UTC').tz_convert(KST)
        else:
            divs.index = divs.index.tz_convert(KST)
        divs.index = divs.index.normalize()
        
    return close_df, divs, ticker_id

df, dividends, ETF_TICKER = load_data_v5()

# 리밸런싱일 계산 함수
def get_rebalance_days(idx):
    r_dates = []
    # 월별 그룹화 후 둘째 금요일 계산
    groups = idx.to_series().groupby(pd.Grouper(freq='ME'))
    for _, group in groups:
        if group.empty: continue
        d1 = group.iloc[0].replace(day=1)
        # 2nd Thu + 1 day = Friday
        w = d1.weekday()
        first_thu = d1 + timedelta(days=((3 - w + 7) % 7))
        sec_thu = first_thu + timedelta(days=7)
        fri = sec_thu + timedelta(days=1)
        
        # 실제 거래일 중 가장 가까운 날짜 찾기
        target_idx = idx.get_indexer([fri], method='nearest')[0]
        r_dates.append(idx[target_idx])
    return sorted(list(set(r_dates)))

if not df.empty:
    re_days = get_rebalance_days(df.index)
    last_re = re_days[-1]
    curr_df = df.loc[df.index >= last_re]
    
    base_p = float(curr_df['^KS200'].iloc[0]) 
    curr_p = float(curr_df['^KS200'].iloc[-1])
    target_p = base_p * 1.05
    profit = ((curr_p - base_p) / base_p) * 100

    # 3. 상단 지표 (순서: 기준 -> 목표 -> 현재 -> 기준지수대비)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("기준 지수", f"{base_p:.2f}", help=f"기준일: {last_re.strftime('%Y-%m-%d')}")
    
    t_diff = target_p - curr_p
    t_label, t_color = ("🔥 초과 상태 중", "normal") if t_diff <= 0 else (f"{t_diff:.2f} 남음", "inverse")
    c2.metric("목표 지수 (5%)", f"{target_p:.2f}", delta=t_label, delta_color=t_color)
    
    c3.metric("현재 지수", f"{curr_p:.2f}", delta=f"{curr_p - base_p:+.2f}")
    c4.metric("기준지수대비", f"{profit:.2f}%")

    # 4. 차트 시각화
    st.subheader("📈 지수 vs ETF 수익률 (KST 기준 및 분배락 표기)")
    fig = go.Figure()
    logs, now_kst = [], datetime.now(KST)

    # 범례 고정
    fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers', 
                             marker=dict(color='green', symbol='star', size=10), name='분배락일(★)'))

    for i, r_day in enumerate(re_days):
        if i + 1 < len(re_days):
            nxt = re_days[i+1]
            tmp = df.loc[(df.index >= r_day) & (df.index < nxt)].copy()
        else:
            tmp = df.loc[df.index >= r_day].copy()
        
        if not tmp.empty:
            s_idx = float(tmp['^KS200'].iloc[0])
            s_etf = float(tmp[ETF_TICKER].iloc[0])
            tmp['Adj'] = (tmp[ETF_TICKER] / s_etf) * s_idx
            
            fig.add_trace(go.Scatter(x=tmp.index, y=tmp['^KS200'], name="KOSPI 200", 
                                     line=dict(color='lightgray', width=1), showlegend=(i==0)))
            fig.add_trace(go.Scatter(x=tmp.index, y=tmp['Adj'], name="TIGER 커버드콜", 
                                     line=dict(color='blue', width=1), showlegend=(i==0)))
            
            # 분배락 표시 (모든 데이터가 KST 꼬리표를 달고 있어 안전함)
            if not dividends.empty:
                d_in_seg = dividends[(dividends.index >= tmp.index[0]) & (dividends.index <= tmp.index[-1])]
                for d_dt, _ in d_in_seg.items():
                    # 가장 가까운 날짜 매칭
                    idx_loc = tmp.index.get_indexer([d_dt], method='nearest')[0]
                    target_dt = tmp.index[idx_loc]
                    fig.add_vline(x=target_dt, line_width=1, line_dash="dot", line_color="green", opacity=0.6)
                    fig.add_trace(go.Scatter(x=[target_dt], y=[tmp.loc[target_dt, 'Adj']], mode='markers', 
                                             marker=dict(color='green', size=10, symbol='star'), showlegend=False))
            
            # 목표선 및 삼각형
            tp = s_idx * 1.05
            fig.add_shape(type="line", x0=tmp.index[0], x1=tmp.index[-1], y0=tp, y1=tp, 
                          line=dict(color="Red", width=1.2, dash="dot"))
            
            hits = tmp[tmp['^KS200'] >= tp]
            if not hits.empty:
                fig.add_trace(go.Scatter(x=hits.index, y=hits['^KS200'].values, mode='markers', 
                                         marker=dict(color='orange', symbol='triangle-up', size=10), showlegend=False))
                for dt, row in hits.iterrows():
                    dt_date = dt.date()
                    is_t = dt_date == now_kst.date()
                    if dt_date < SYSTEM_START_DATE: st_val = "⚪ 미실행"
                    elif is_t and now_kst.hour < 15: st_val = "⏳ 발송 예정"
                    else: st_val = "✅ 발송 성공"
                    logs.append({"날짜": dt.strftime('%Y-%m-%d'), "지수": f"{row['^KS200']:.2f}", "상태": st_val})

    fig.update_layout(height=550, template="plotly_white", hovermode="x unified", 
                      legend=dict(orientation="h", y=1.1, x=1))
    st.plotly_chart(fig, use_container_width=True)

    # 5. 하단 테이블
    l_col, d_col = st.columns(2)
    with l_col:
        st.subheader("🔔 실행 로그")
        if logs: st.dataframe(pd.DataFrame(logs).sort_values("날짜", ascending=False), use_container_width=True, hide_index=True)
    with d_col:
        st.subheader("💰 최근 분배금 이력")
        if not dividends.empty:
            d_df = dividends.reset_index()
            d_df.columns = ['배당락일', '원']
            # 보기 편하게 날짜 형식 변경
            d_df['배당락일'] = d_df['배당락일'].dt.strftime('%Y-%m-%d')
            st.dataframe(d_df.sort_values('배당락일', ascending=False).head(10), use_container_width=True, hide_index=True)

    st.info(f"마지막 업데이트: {df.index[-1].strftime('%Y-%m-%d %H:%M')} (KST)")
else:
    st.error("데이터 로드 실패")
