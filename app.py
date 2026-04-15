import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# 1. 페이지 설정 및 제목
st.set_page_config(page_title="KOSPI 200 전략 모니터", layout="wide")
st.title("📊 KOSPI 200 전략 모니터 (v4.1)")

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

with st.sidebar:
    st.header("🛠 시스템 설정")
    if st.button("📲 텔레그램 테스트 문자 발송"): send_telegram_test()

# 2. 데이터 로드 및 정규화 (최대한 단순한 구조로 변경)
ticker_id = "166400.KS"
tickers = ["^KS200", ticker_id]

@st.cache_data(ttl=3600)
def load_data():
    raw = yf.download(tickers, period="1y", progress=False)
    # 인덱스를 순수한 날짜로 변경
    raw.index = pd.to_datetime(raw.index).tz_localize(None).normalize()
    
    close_df = raw['Close'].copy()
    if isinstance(close_df.columns, pd.MultiIndex):
        close_df.columns = close_df.columns.get_level_values(0)
    
    # 중복 제거 및 정렬 (판다스 에러 방지)
    close_df = close_df[~close_df.index.duplicated(keep='first')].sort_index()
    
    info = yf.Ticker(ticker_id)
    divs = info.dividends
    if not divs.empty:
        divs.index = pd.to_datetime(divs.index).tz_localize(None).normalize()
    return close_df, divs

df, dividends = load_data()

# 리밸런싱일 계산 함수
def get_rebalance_days(idx):
    r_dates = []
    # 월별 그룹화 후 둘째 금요일 계산
    groups = idx.to_series().groupby(pd.Grouper(freq='ME'))
    for _, group in groups:
        if group.empty: continue
        d1 = group.iloc[0].replace(day=1)
        w = d1.weekday()
        first_thu = d1 + timedelta(days=((3 - w + 7) % 7))
        sec_thu = first_thu + timedelta(days=7)
        fri = sec_thu + timedelta(days=1)
        # 실제 거래일 중에 있는지 확인 (없으면 가장 가까운 미래 거래일)
        if fri in idx:
            r_dates.append(fri)
        else:
            future_days = idx[idx >= fri]
            if not future_days.empty:
                r_dates.append(future_days[0])
    return r_dates

if not df.empty:
    re_days = get_rebalance_days(df.index)
    last_re = re_days[-1]
    curr_df = df.loc[df.index >= last_re]
    
    base_p = float(curr_df['^KS200'].iloc[0]) 
    curr_p = float(curr_df['^KS200'].iloc[-1])
    target_p = base_p * 1.05
    profit = ((curr_p - base_p) / base_p) * 100

    # 3. 상단 지표 (기준 -> 목표 -> 현재 -> 기준지수대비)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("기준 지수", f"{base_p:.2f}")
    
    t_diff = target_p - curr_p
    t_label, t_color = ("🔥 초과 상태 중", "normal") if t_diff <= 0 else (f"{t_diff:.2f} 남음", "inverse")
    c2.metric("목표 지수 (5%)", f"{target_p:.2f}", delta=t_label, delta_color=t_color)
    
    c3.metric("현재 지수", f"{curr_p:.2f}", delta=f"{curr_p - base_p:+.2f}")
    c4.metric("기준지수대비", f"{profit:.2f}%")

    # 4. 차트 시각화
    st.subheader("📈 지수 vs ETF 수익률 동기화 (분배락 표기)")
    fig = go.Figure()
    logs, now = [], datetime.now()

    # 범례 고정
    fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers', 
                             marker=dict(color='green', symbol='star', size=10), name='분배락일(★)'))

    for i, r_day in enumerate(re_days):
        nxt = re_days[i+1] if i+1 < len(re_days) else df.index[-1]
        tmp = df.loc[(df.index >= r_day) & (df.index <= nxt)].copy()
        
        if not tmp.empty:
            s_idx, s_etf = float(tmp['^KS200'].iloc[0]), float(tmp[ticker_id].iloc[0])
            tmp['Adj'] = (tmp[ticker_id] / s_etf) * s_idx
            
            fig.add_trace(go.Scatter(x=tmp.index, y=tmp['^KS200'], name="KOSPI 200", 
                                     line=dict(color='lightgray', width=1), showlegend=(i==0)))
            fig.add_trace(go.Scatter(x=tmp.index, y=tmp['Adj'], name="TIGER 커버드콜", 
                                     line=dict(color='blue', width=1), showlegend=(i==0)))
            
            # [수정] 분배락 표시 로직: 에러 유발 함수 제거 후 수동 매칭
            if not dividends.empty:
                d_in_seg = dividends[(dividends.index >= tmp.index[0]) & (dividends.index <= tmp.index[-1])]
                for d_dt, _ in d_in_seg.items():
                    # tmp.index의 날짜들과 d_dt 사이의 절대 거리 계산 (수동)
                    # 두 날짜 모두 Naive 상태임을 보장
                    available_dates = tmp.index.to_list()
                    target_dt = min(available_dates, key=lambda x: abs((x - d_dt).total_seconds()))
                    
                    fig.add_vline(x=target_dt, line_width=1, line_dash="dot", line_color="green", opacity=0.6)
                    fig.add_trace(go.Scatter(x=[target_dt], y=[tmp.loc[target_dt, 'Adj']], mode='markers', 
                                             marker=dict(color='green', size=10, symbol='star'), showlegend=False))
            
            # 목표선 및 삼각형
            tp = s_idx * 1.05
            fig.add_shape(type="line", x0=tmp.index[0], x1=temp_x1 := tmp.index[-1], y0=tp, y1=tp, 
                          line=dict(color="Red", width=1, dash="dot"))
            
            hits = tmp[tmp['^KS200'] >= tp]
            if not hits.empty:
                fig.add_trace(go.Scatter(x=hits.index, y=hits['^KS200'].values, mode='markers', 
                                         marker=dict(color='orange', symbol='triangle-up', size=10), showlegend=False))
                for dt, row in hits.iterrows():
                    dt_date = dt.date()
                    is_t = dt_date == now.date()
                    if dt_date < SYSTEM_START_DATE: st_val = "⚪ 미실행"
                    elif is_t and now.hour < 15: st_val = "⏳ 발송 예정"
                    else: st_val = "✅ 발송 성공"
                    logs.append({"날짜": dt.strftime('%Y-%m-%d'), "지수": f"{row['^KS200']:.2f}", "상태": st_val})

    fig.update_layout(height=550, template="plotly_white", hovermode="x unified", legend=dict(orientation="h", y=1.1, x=1))
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
            st.dataframe(d_df.sort_values('배당락일', ascending=False).head(10), use_container_width=True, hide_index=True)

    st.info(f"업데이트: {df.index[-1].strftime('%Y-%m-%d %H:%M')}")
else:
    st.error("데이터 로드 실패")
