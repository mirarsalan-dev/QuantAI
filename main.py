import time
import threading
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx
import requests
from google.cloud.firestore import FieldFilter
from google.cloud import firestore as gcf
import os

# 🛑 Force UTF-8 encoding for Windows paths
os.environ["PYTHONUTF8"] = "1"

# internal modules
from config import logger, db, LOOKBACK_DAYS, TRAIN_TEST_SPLIT, FIREBASE_AVAILABLE
from auth import login_user, create_user
from financial import (
    fetch_company_profile,
    resolve_ticker,
    fetch_market_data, 
    train_and_cache_model,
    get_exchange_rate,
    get_stock_news,
)
from ui import safe_markdown, display_news, sanitize_ticker

# ==========================================
# PAGE CONFIGURATION (Must be first)
# ==========================================
st.set_page_config(page_title="QuantAI Suite", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 🛡️ SECURITY: DUAL-LAYER RATE LIMITER
# ==========================================
@st.cache_resource
def get_rate_limiter():
    return {'global_hits': [], 'session_hits': {}, 'lock': threading.Lock()}

def enforce_rate_limit(max_requests=30, time_window=60.0):
    store = get_rate_limiter()
    ctx = get_script_run_ctx()
    session_id = ctx.session_id if ctx else "headless_bot"
    now = time.time()

    with store['lock']:
        valid_global = [ts for ts in store['global_hits'] if now - ts < time_window]
        if session_id not in store['session_hits']:
            store['session_hits'][session_id] = []
        valid_session = [ts for ts in store['session_hits'][session_id] if now - ts < time_window]

        if len(valid_global) >= max_requests or len(valid_session) >= max_requests:
            return False

        store['global_hits'] = valid_global + [now]
        store['session_hits'][session_id] = valid_session + [now]
        return True

if not enforce_rate_limit(max_requests=30, time_window=60.0):
    st.error("🚦 RATE LIMIT EXCEEDED: Please wait a moment.")
    st.stop()

# ==========================================
# UNIVERSAL PREMIUM CSS
# ==========================================
st.markdown("""
    <style>
    .gradient-text {
        background: linear-gradient(90deg, var(--primary-color), #8B5CF6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 3.2rem !important;
        font-weight: 900 !important;
        text-align: center;
        margin-bottom: 0rem;
    }
    .gradient-header {
        background: linear-gradient(90deg, var(--primary-color), #8B5CF6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.2rem !important;
        font-weight: 800 !important;
        margin-bottom: 0.1rem;
    }
    .sub-text { text-align: center; color: var(--text-color); opacity: 0.7; font-size: 1.1rem; margin-bottom: 2rem; }
    .sub-header { font-size: 1.0rem !important; color: var(--text-color); opacity: 0.7; margin-bottom: 2rem; }
    div[data-testid="stMetric"] { background: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); padding: 1.2rem 1.5rem; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); transition: all 0.3s ease; }
    div[data-testid="stMetric"]:hover { transform: translateY(-4px); box-shadow: 0 8px 15px rgba(0,0,0,0.1); border-color: var(--primary-color); }
    div[data-testid="stMetricValue"] { font-size: 1.6rem !important; font-weight: 700 !important; }
    div[data-testid="stExpander"] { border: 1px solid rgba(128, 128, 128, 0.2) !important; border-radius: 10px !important; }
    .news-card { background: var(--secondary-background-color); padding: 15px; border-radius: 10px; border-left: 4px solid var(--primary-color); margin-bottom: 12px; border-top: 1px solid rgba(128,128,128,0.1); border-right: 1px solid rgba(128,128,128,0.1); border-bottom: 1px solid rgba(128,128,128,0.1); }
    .news-card a { color: var(--text-color); text-decoration: none; font-weight: 600; font-size: 1.1rem; }
    .news-card a:hover { color: var(--primary-color); text-decoration: underline; }
    .news-publisher { font-size: 0.85rem; opacity: 0.6; margin-top: 5px; }
    </style>
""", unsafe_allow_html=True)


if not FIREBASE_AVAILABLE:
    st.title("QuantAI — Firebase Required")
    st.error("Firebase is not configured. This app requires a valid Firebase service account JSON file named 'firebase_key.json' in the workspace root.")
    st.stop()

# ==========================================
# UI ROUTING: HARD AUTHENTICATION GATE
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.markdown('<style>[data-testid="stSidebar"] { display: none; }</style>', unsafe_allow_html=True)
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.container():
            st.markdown('<div class="gradient-text">QuantAI</div>', unsafe_allow_html=True)
            st.markdown('<div class="sub-text">Institutional-Grade Predictive Engine</div>', unsafe_allow_html=True)
            auth_action = st.radio("Action", ["Sign In", "Create Account"], horizontal=True, label_visibility="collapsed")
            st.markdown("<br>", unsafe_allow_html=True)
            if auth_action == "Sign In":
                login_user_input = st.text_input("Username", key="login_user")
                login_pass_input = st.text_input("Password", type="password", key="login_pass")
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Authenticate Session", type="primary", use_container_width=True):
                    if login_user(login_user_input, login_pass_input):
                        st.session_state['logged_in'] = True
                        st.session_state['username'] = login_user_input
                        st.success("✅ Secure connection established! Booting AI Terminal...")
                        st.rerun()
                    else:
                        st.error("Access Denied.")
            else:
                new_user_input = st.text_input("Choose Username", key="reg_user")
                new_pass_input = st.text_input("Choose Password", type="password", key="reg_pass")
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Initialize Secure Profile", type="secondary", use_container_width=True):
                    if len(new_user_input) < 3 or len(new_pass_input) < 4:
                        st.warning("Username: 3+ chars. Password: 4+ chars.")
                    elif create_user(new_user_input, new_pass_input):
                        st.success("Created! Switch to 'Sign In'.")
                    else:
                        st.error("Username already exists or DB unavailable.")
    st.stop()


import plotly.graph_objects as go
import io
import json
from datetime import date, timedelta
import numpy as np
import pandas as pd

# ==========================================
# CLOUD HISTORY FUNCTIONS
# ==========================================
def save_search(username: str, ticker: str):
    if db is None: return
    doc_id = f"{username}_{ticker}"
    doc_ref = db.collection('history').document(doc_id)
    try:
        transaction = db.transaction()
        @gcf.transactional
        def update_in_transaction(transaction, doc_ref):
            snap = doc_ref.get(transaction=transaction)
            if not snap.exists:
                transaction.set(doc_ref, {'username': username, 'ticker': ticker, 'timestamp': gcf.SERVER_TIMESTAMP})
        update_in_transaction(transaction, doc_ref)
    except Exception:
        pass

def get_search_history(username: str):
    if db is None: return []
    try:
        query = db.collection('history').where(filter=FieldFilter('username', '==', username)).order_by('timestamp', direction=gcf.Query.DESCENDING).get()
        return [doc.to_dict().get('ticker') for doc in query]
    except Exception:
        try:
            query = db.collection('history').where(filter=FieldFilter('username', '==', username)).get()
            return [doc.to_dict().get('ticker') for doc in query]
        except Exception:
            return []

def format_large_number(num):
    if not num or num == 'N/A': return "N/A"
    try:
        num = float(num)
        if num >= 1e12: return f"{num/1e12:.2f} Trillion"
        if num >= 1e9: return f"{num/1e9:.2f} Billion"
        if num >= 1e6: return f"{num/1e6:.2f} Million"
        return f"{num:,.2f}"
    except: return "N/A"

# ==========================================
# UI ROUTING: MAIN DASHBOARD
# ==========================================
st.markdown('<div class="gradient-header">QuantAI Workspace</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-header">Active Cloud Node Connection: <b>{st.session_state["username"]}</b></div>', unsafe_allow_html=True)

st.sidebar.markdown(f"👤 **Account:** `{st.session_state['username']}`")
if st.sidebar.button("Log Out", type="secondary", use_container_width=True):
    st.session_state.clear()
    st.rerun()
st.sidebar.markdown("---")

st.sidebar.markdown("### 🔍 Search Market")
raw_search = st.sidebar.text_input("Company Name or Symbol", value=st.session_state.get('active_ticker', "AAPL"))
user_ticker = sanitize_ticker(raw_search)
user_ticker = resolve_ticker(user_ticker)
st.session_state['active_ticker'] = user_ticker
save_search(st.session_state['username'], user_ticker)

st.sidebar.markdown("### 💰 Portfolio Setup")
investment_budget = st.sidebar.number_input("Investment Capital", min_value=10.0, value=1000.0, step=100.0)

st.sidebar.markdown("### 🌍 Display Options")
selected_currency = st.sidebar.selectbox("Local Currency", ["USD", "EUR", "GBP", "INR", "JPY", "CAD", "AUD"])
time_interval = st.sidebar.selectbox("Timeframe", options=["1d", "1h", "15m"], format_func=lambda x: "Long Term (Daily)" if x=="1d" else "Day Trading (Hourly)" if x=="1h" else "Scalping (15-Minute)")

with st.sidebar.expander("⚙️ Advanced AI Settings"):
    start_date = st.sidebar.date_input("Training Start Date", value=date.today() - timedelta(days=365 * 3))
    look_back = st.slider("Memory Window", 30, 90, 60)
    training_epochs = st.slider("Epochs", 3, 15, 5)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🕒 Recent Searches")
history = get_search_history(st.session_state['username'])
for past_ticker in history[:5] if history else []: 
    if st.sidebar.button(f"🔍 {past_ticker}", key=f"hist_{past_ticker}", use_container_width=True):
        st.session_state['active_ticker'] = past_ticker
        st.rerun() 

# ==========================================
# EXECUTION LOGIC 
# ==========================================
try:
    profile = fetch_company_profile(user_ticker)
    if profile:
        company_name, sector = profile['name'], profile['sector']
        summary, market_cap = profile['summary'], profile['market_cap']
        pe_ratio, high_52, low_52 = profile['pe_ratio'], profile['high_52'], profile['low_52']
        live_price = profile['live_price']
    else:
        company_name, sector, summary, live_price = user_ticker, "Unknown", "No data.", 0.0
        market_cap, pe_ratio, high_52, low_52 = "N/A", "N/A", "N/A", "N/A"
    news_data = get_stock_news(user_ticker, company_name)
except Exception:
    company_name, sector, summary, live_price, news_data = user_ticker, "Unknown", "No data.", 0.0, []

try:
    df_data = fetch_market_data(user_ticker, start_date, date.today(), interval=time_interval)
    
    if df_data.empty:
        st.error(f"No market data could be downloaded for '{user_ticker}'.")
        st.stop()
        
    closes = df_data['Close'].copy()
    min_timeframe_price_usd = df_data['Low'].min()
    
    try:
        with st.spinner(f"🧠 AI is studying market patterns for {company_name}..."):
            # 🛑 Nuclear Fix: Only 2 returns expected, uses look_back directly
            model, targ_scaler = train_and_cache_model(user_ticker, time_interval, look_back, training_epochs)

        X = []
        y = []
        
        # 🛑 Uses look_back directly
        for i in range(look_back, len(closes)):
            X.append(closes.iloc[i - look_back:i].values)
            y.append(closes.iloc[i])
            
        # 🛑 Tuple Safety Catch
        if len(X) == 0:
            raise ValueError("Not enough data in this timeframe for the AI memory window.")
            
        X = np.array(X)
        y = np.array(y)
        X_flat = X.reshape(X.shape[0], X.shape[1])
        train_len = int(np.ceil(len(X_flat) * TRAIN_TEST_SPLIT))

        with st.spinner("⚡ Forecasting future price..."):
            x_test = X_flat[train_len:]
            X_future = X_flat[-1].reshape(1, -1)
            preds_scaled = model.predict(x_test)
            future_pred_scaled = model.predict(X_future)

        model_predictions_usd = targ_scaler.inverse_transform(np.array(preds_scaled).reshape(-1, 1)).ravel()
        tomorrow_pred_usd = float(targ_scaler.inverse_transform(np.array(future_pred_scaled).reshape(-1, 1)).ravel()[0])
        if len(y[train_len:]) > 0:
            rmse_score_usd = np.sqrt(np.mean((model_predictions_usd - y[train_len:]) ** 2))
        else:
            rmse_score_usd = 0.0

    except ValueError:
        st.warning("Not enough data for AI model; using simpler persistence forecast for chart.")
        train_len = 1
        preds = closes.shift(1).iloc[train_len:]
        model_predictions_usd = preds.values
        tomorrow_pred_usd = float(closes.iloc[-1])
        actuals = closes.iloc[train_len:]
        if len(actuals) > 0 and len(model_predictions_usd) == len(actuals):
            rmse_score_usd = np.sqrt(np.mean((model_predictions_usd - actuals.values) ** 2))
        else:
            rmse_score_usd = 0.0
    
    fx_rate, fx_sym = get_exchange_rate(selected_currency)
    live_price_cv = live_price * fx_rate
    tomorrow_pred_cv = tomorrow_pred_usd * fx_rate
    rmse_score_cv = rmse_score_usd * fx_rate
    min_price_cv = min_timeframe_price_usd * fx_rate 
    
    tech_score = 50
    try:
        if df_data['RSI_14'].iloc[-1] < 40: tech_score += 25
        elif df_data['RSI_14'].iloc[-1] > 60: tech_score -= 25
        if df_data['MACD'].iloc[-1] > df_data['MACD_Signal'].iloc[-1]: tech_score += 15
        else: tech_score -= 15
        if df_data['Close'].iloc[-1] > df_data['SMA_20'].iloc[-1]: tech_score += 10
        else: tech_score -= 10
    except (KeyError, IndexError):
        pass
    tech_score = max(0, min(100, tech_score))
    
    def render_dashboard(company_name, sector, user_ticker, df_data, model_predictions_usd, train_len, tomorrow_pred_usd, rmse_score_usd, news_data, live_price, market_cap, pe_ratio, high_52, low_52, selected_currency, investment_budget, username, tech_score):
        fx_rate, fx_sym = get_exchange_rate(selected_currency)
        live_price_cv = live_price * fx_rate
        tomorrow_pred_cv = tomorrow_pred_usd * fx_rate
        rmse_score_cv = rmse_score_usd * fx_rate
        min_price_cv = df_data['Low'].min() * fx_rate if 'Low' in df_data.columns else 0.0

        st.markdown(f"### 🏢 {company_name} (`{user_ticker}`)")
        st.caption(f"**Industry:** {sector} | **AI Timeframe:** {time_interval}")
        m1, m2, m3, m4 = st.columns(4)
        dir_text = "🟢 BULLISH" if tomorrow_pred_usd > df_data['Close'].iloc[-1] else "🔴 BEARISH"

        m1.metric(f"Current Live Price ({selected_currency})", f"{fx_sym}{live_price_cv:.2f}" if live_price > 0 else "Closed")
        m2.metric("AI Forecast", f"{fx_sym}{tomorrow_pred_cv:.2f}", f"Trend: {dir_text}")
        m3.metric("Minimum Price", f"{fx_sym}{min_price_cv:.2f}")
        m4.metric("AI Error Margin", f"± {fx_sym}{rmse_score_cv:.2f}")

        if live_price > 0:
            afford = investment_budget / live_price_cv if live_price_cv != 0 else 0.0
            pnl_amt = (afford * tomorrow_pred_cv) - investment_budget
            pnl_pct = (pnl_amt / investment_budget) * 100 if investment_budget != 0 else 0.0
            stop_loss = live_price_cv - rmse_score_cv
            r_text, r_col = ("🟢 BUY RECOMMENDED", "#2ECC71") if pnl_pct > 0.5 else ("🔴 AVOID / SELL", "#E74C3C") if pnl_pct < -0.5 else ("🟡 NEUTRAL / HOLD", "#F1C40F")

            st.markdown(f"""
                <div style="background: var(--secondary-background-color); padding: 20px; border-radius: 12px; border-left: 6px solid {r_col}; margin: 15px 0 25px 0; border-top: 1px solid rgba(128,128,128,0.2); border-right: 1px solid rgba(128,128,128,0.2); border-bottom: 1px solid rgba(128,128,128,0.2); box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                    <h4 style="margin-top:0px; color:{r_col}; font-weight: 800;">{r_text}</h4>
                    <p style="margin-bottom:8px; font-size:1.1rem;">Budget <b>{fx_sym}{investment_budget:,.2f}</b> = <b>{afford:,.4f} shares</b>.</p>
                    <p style="margin-bottom:0px; font-size:1.1rem;">Projected PnL: <b style="color:{r_col};">{fx_sym}{pnl_amt:+,.2f} ({pnl_pct:+,.2f}%)</b>. AI Stop-Loss calculated at: <b>{fx_sym}{stop_loss:,.2f}</b>.</p>
                </div>
            """, unsafe_allow_html=True)

        t1, t2, t3, t4 = st.tabs(["📈 AI Forecast", "🧭 Technical Radar", "🗞️ Live News", "ℹ️ Company & Data"])
        with t1:
            eval_df = df_data.iloc[-len(model_predictions_usd):].copy()
            eval_df['Close_Cv'] = eval_df['Close'] * fx_rate
            eval_df['Preds_Cv'] = model_predictions_usd * fx_rate

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=eval_df.index, y=eval_df['Close_Cv'], name="Market Price", line=dict(color='#2ECC71', width=2)))
            fig.add_trace(go.Scatter(x=eval_df.index, y=eval_df['Preds_Cv'], name="AI Prediction", line=dict(color='#8B5CF6', dash='dash')))
            fig.update_layout(xaxis_title="Time", yaxis_title=f"Price ({selected_currency})", hovermode="x unified", margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True, theme="streamlit")
            st.markdown("### Model Predictions")
            st.dataframe(eval_df.reset_index(), use_container_width=True)

        with t2:
            c_left, c_right = st.columns([1, 1])
            with c_left:
                gauge = go.Figure(go.Indicator(
                    mode = "gauge+number", value = tech_score, title = {'text': "Momentum Score"},
                    gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "rgba(255,255,255,0.4)"},
                             'steps' : [{'range': [0, 35], 'color': "#E74C3C"}, {'range': [35, 65], 'color': "#F1C40F"}, {'range': [65, 100], 'color': "#2ECC71"}]}
                ))
                gauge.update_layout(height=350, margin=dict(l=20, r=20, t=50, b=20))
                st.plotly_chart(gauge, use_container_width=True, theme="streamlit")
            with c_right:
                st.markdown("<br><br>", unsafe_allow_html=True)
                st.markdown("#### Radar Breakdown")
                st.markdown(f"- **RSI (Relative Strength):** {df_data['RSI_14'].iloc[-1]:.2f}")
                st.markdown(f"- **MACD Trend:** {'Bullish (Above Signal)' if df_data['MACD'].iloc[-1] > df_data['MACD_Signal'].iloc[-1] else 'Bearish (Below Signal)'}")
                st.markdown(f"- **20-Day Average:** {'Price is holding above average' if df_data['Close'].iloc[-1] > df_data['SMA_20'].iloc[-1] else 'Price crashed below average'}")
                st.markdown("---")

        with t3:
            st.markdown("### Latest Market Headlines")
            if not news_data: st.info("No recent news found for this asset right now.")
            else: display_news(news_data)

        with t4:
            st.markdown("### Fundamental Statistics")
            f1, f2, f3, f4 = st.columns(4)
            f1.metric("Market Cap", f"{format_large_number(market_cap)}")
            f2.metric("P/E Ratio", f"{pe_ratio}")
            f3.metric("52-Week High", f"${high_52}")
            f4.metric("52-Week Low", f"${low_52}")

            with st.expander("Read Company Profile"):
                safe_markdown(summary)
            st.markdown("---")
            st.dataframe(df_data[['Close', 'Volume', 'SMA_20', 'RSI_14', 'MACD']].tail(200), use_container_width=True)

    render_dashboard(company_name, sector, user_ticker, df_data, model_predictions_usd, train_len, tomorrow_pred_usd, rmse_score_usd, news_data, live_price, market_cap, pe_ratio, high_52, low_52, selected_currency, investment_budget, st.session_state['username'], tech_score)

except ValueError as e:
    st.info("⚠️ Modeling notice: not enough data to train the AI for this timeframe. Showing fallback persistence forecast.")
    try:
        closes = df_data['Close'].copy()
        train_len = 1
        preds = closes.shift(1).iloc[train_len:]
        model_predictions_usd = preds.values
        tomorrow_pred_usd = float(closes.iloc[-1])
        actuals = closes.iloc[train_len:]
        rmse_score_usd = np.sqrt(np.mean((model_predictions_usd - actuals.values) ** 2)) if len(actuals) > 0 else 0.0

        render_dashboard(company_name, sector, user_ticker, df_data, model_predictions_usd, train_len, tomorrow_pred_usd, rmse_score_usd, news_data, live_price, market_cap, pe_ratio, high_52, low_52, selected_currency, investment_budget, st.session_state.get('username', 'guest'), 50)
    except Exception:
        st.error("No market data available to render fallback chart.")
except Exception as e:
    st.info("ℹ️ The AI encountered an unexpected issue while reading data. Try a different company or timeframe.")
    with st.expander("Error details"):
        st.write(str(e))