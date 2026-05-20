import time
import threading
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx
import requests
from google.cloud.firestore import FieldFilter
from google.cloud import firestore as gcf
import os
import plotly.graph_objects as go
import numpy as np
import pandas as pd
from datetime import date, timedelta

# Force UTF-8 encoding for Windows paths
os.environ["PYTHONUTF8"] = "1"

# Internal modules
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
# CONFIGURATION & CONSTANTS
# ==========================================
st.set_page_config(page_title="QuantAI Suite", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

# Rate Limiting
RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_WINDOW = 60.0

# Technical Score Weights
TECH_SCORE_BASE = 50
RSI_OVERSOLD_BONUS = 25
RSI_OVERBOUGHT_PENALTY = 25
MACD_BULLISH_BONUS = 15
SMA_ABOVE_BONUS = 10

# PnL Thresholds
BUY_RECOMMENDATION_THRESHOLD = 0.5
SELL_RECOMMENDATION_THRESHOLD = -0.5

# ==========================================
# STATE MANAGEMENT
# ==========================================
class SessionManager:
    @staticmethod
    def init():
        if 'app_state' not in st.session_state:
            st.session_state['app_state'] = {
                'logged_in': False,
                'username': None,
                'active_ticker': 'AAPL'
            }
            
    @staticmethod
    def is_logged_in():
        return st.session_state['app_state'].get('logged_in', False)
        
    @staticmethod
    def login(username):
        st.session_state['app_state']['logged_in'] = True
        st.session_state['app_state']['username'] = username
        
    @staticmethod
    def logout():
        st.session_state['app_state']['logged_in'] = False
        st.session_state['app_state']['username'] = None
        
    @staticmethod
    def get_username():
        return st.session_state['app_state'].get('username', 'Guest')
        
    @staticmethod
    def get_ticker():
        return st.session_state['app_state'].get('active_ticker', 'AAPL')
        
    @staticmethod
    def set_ticker(ticker):
        st.session_state['app_state']['active_ticker'] = ticker


SessionManager.init()

# ==========================================
# CORE UTILITIES & SECURITY
# ==========================================
@st.cache_resource
def get_rate_limiter():
    return {'global_hits': [], 'session_hits': {}, 'lock': threading.Lock()}

def enforce_rate_limit(max_requests=RATE_LIMIT_REQUESTS, time_window=RATE_LIMIT_WINDOW):
    store = get_rate_limiter()
    ctx = get_script_run_ctx()
    session_id = ctx.session_id if ctx else "headless_bot"
    now = time.time()

    with store['lock']:
        valid_global = [ts for ts in store['global_hits'] if now - ts < time_window]
        valid_session = [ts for ts in store['session_hits'].setdefault(session_id, []) if now - ts < time_window]

        if len(valid_global) >= max_requests or len(valid_session) >= max_requests:
            return False

        store['global_hits'] = valid_global + [now]
        store['session_hits'][session_id] = valid_session + [now]
        return True

def apply_currency_conversion(values_dict, selected_currency):
    """Centralized currency conversion to eliminate redundant API calls and math."""
    fx_rate, fx_sym = get_exchange_rate(selected_currency)
    return {
        'live_price': values_dict.get('live_price', 0) * fx_rate,
        'tomorrow_pred': values_dict.get('tomorrow_pred', 0) * fx_rate,
        'rmse_score': values_dict.get('rmse_score', 0) * fx_rate,
        'min_price': values_dict.get('min_price', 0) * fx_rate,
        'fx_rate': fx_rate,
        'fx_sym': fx_sym
    }

def calculate_technical_score(df_data):
    """Isolate technical scoring logic."""
    score = TECH_SCORE_BASE
    try:
        if df_data['RSI_14'].iloc[-1] < 40: score += RSI_OVERSOLD_BONUS
        elif df_data['RSI_14'].iloc[-1] > 60: score -= RSI_OVERBOUGHT_PENALTY
        
        if df_data['MACD'].iloc[-1] > df_data['MACD_Signal'].iloc[-1]: score += MACD_BULLISH_BONUS
        else: score -= MACD_BULLISH_BONUS
        
        if df_data['Close'].iloc[-1] > df_data['SMA_20'].iloc[-1]: score += SMA_ABOVE_BONUS
        else: score -= SMA_ABOVE_BONUS
    except (KeyError, IndexError):
        pass
    return max(0, min(100, score))

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
# UI RENDERING COMPONENTS
# ==========================================
def inject_custom_css():
    st.markdown("""
        <style>
        .gradient-text { background: linear-gradient(90deg, var(--primary-color), #8B5CF6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 3.2rem !important; font-weight: 900 !important; text-align: center; margin-bottom: 0rem; }
        .gradient-header { background: linear-gradient(90deg, var(--primary-color), #8B5CF6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.2rem !important; font-weight: 800 !important; margin-bottom: 0.1rem; }
        .sub-text { text-align: center; color: var(--text-color); opacity: 0.7; font-size: 1.1rem; margin-bottom: 2rem; }
        .sub-header { font-size: 1.0rem !important; color: var(--text-color); opacity: 0.7; margin-bottom: 2rem; }
        div[data-testid="stMetric"] { background: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); padding: 1.2rem 1.5rem; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); transition: all 0.3s ease; }
        div[data-testid="stMetric"]:hover { transform: translateY(-4px); box-shadow: 0 8px 15px rgba(0,0,0,0.1); border-color: var(--primary-color); }
        div[data-testid="stMetricValue"] { font-size: 1.6rem !important; font-weight: 700 !important; }
        div[data-testid="stExpander"] { border: 1px solid rgba(128, 128, 128, 0.2) !important; border-radius: 10px !important; }
        </style>
    """, unsafe_allow_html=True)

def render_auth_gate():
    st.markdown('<style>[data-testid="stSidebar"] { display: none; }</style>', unsafe_allow_html=True)
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown('<div class="gradient-text">QuantAI</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub-text">Institutional-Grade Predictive Engine</div>', unsafe_allow_html=True)
        auth_action = st.radio("Action", ["Sign In", "Create Account"], horizontal=True, label_visibility="collapsed")
        
        if auth_action == "Sign In":
            user_in = st.text_input("Username", key="login_user")
            pass_in = st.text_input("Password", type="password", key="login_pass")
            if st.button("Authenticate Session", type="primary", use_container_width=True):
                if login_user(user_in, pass_in):
                    SessionManager.login(user_in)
                    st.success("✅ Secure connection established! Booting AI Terminal...")
                    st.rerun()
                else: st.error("Access Denied.")
        else:
            new_user = st.text_input("Choose Username", key="reg_user")
            new_pass = st.text_input("Choose Password", type="password", key="reg_pass")
            if st.button("Initialize Secure Profile", type="secondary", use_container_width=True):
                if create_user(new_user, new_pass): st.success("Created! Switch to 'Sign In'.")
                else: st.error("Registration failed.")
    st.stop()

def render_price_metrics(company_name, sector, user_ticker, time_interval, df_data, cv_data):
    st.markdown(f"### 🏢 {company_name} (`{user_ticker}`)")
    st.caption(f"**Industry:** {sector} | **AI Timeframe:** {time_interval}")
    m1, m2, m3, m4 = st.columns(4)
    
    dir_text = "🟢 BULLISH" if cv_data['tomorrow_pred'] > (df_data['Close'].iloc[-1] * cv_data['fx_rate']) else "🔴 BEARISH"
    m1.metric(f"Live Price", f"{cv_data['fx_sym']}{cv_data['live_price']:.2f}")
    m2.metric("AI Forecast", f"{cv_data['fx_sym']}{cv_data['tomorrow_pred']:.2f}", f"Trend: {dir_text}")
    m3.metric("Minimum Price", f"{cv_data['fx_sym']}{cv_data['min_price']:.2f}")
    m4.metric("AI Error Margin", f"± {cv_data['fx_sym']}{cv_data['rmse_score']:.2f}")

def render_trade_card(cv_data, investment_budget):
    if cv_data['live_price'] <= 0: return
    
    afford = investment_budget / cv_data['live_price']
    pnl_amt = (afford * cv_data['tomorrow_pred']) - investment_budget
    pnl_pct = (pnl_amt / investment_budget) * 100 if investment_budget > 0 else 0
    stop_loss = cv_data['live_price'] - cv_data['rmse_score']
    
    if pnl_pct > BUY_RECOMMENDATION_THRESHOLD: r_text, r_col = "🟢 BUY RECOMMENDED", "#2ECC71"
    elif pnl_pct < SELL_RECOMMENDATION_THRESHOLD: r_text, r_col = "🔴 AVOID / SELL", "#E74C3C"
    else: r_text, r_col = "🟡 NEUTRAL / HOLD", "#F1C40F"

    st.markdown(f"""
        <div style="background: var(--secondary-background-color); padding: 20px; border-radius: 12px; border-left: 6px solid {r_col}; margin: 15px 0 25px 0;">
            <h4 style="margin-top:0px; color:{r_col};">{r_text}</h4>
            <p style="margin-bottom:8px;">Budget <b>{cv_data['fx_sym']}{investment_budget:,.2f}</b> = <b>{afford:,.4f} shares</b>.</p>
            <p style="margin-bottom:0px;">Projected PnL: <b style="color:{r_col};">{cv_data['fx_sym']}{pnl_amt:+,.2f} ({pnl_pct:+,.2f}%)</b>. AI Stop-Loss: <b>{cv_data['fx_sym']}{stop_loss:,.2f}</b>.</p>
        </div>
    """, unsafe_allow_html=True)

def render_forecast_tab(df_data, model_predictions_usd, selected_currency, cv_data):
    eval_df = df_data.iloc[-len(model_predictions_usd):].copy()
    eval_df['Close_Cv'] = eval_df['Close'] * cv_data['fx_rate']
    eval_df['Preds_Cv'] = model_predictions_usd * cv_data['fx_rate']

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=eval_df.index, y=eval_df['Close_Cv'], name="Market Price", line=dict(color='#2ECC71', width=2)))
    fig.add_trace(go.Scatter(x=eval_df.index, y=eval_df['Preds_Cv'], name="AI Prediction", line=dict(color='#8B5CF6', dash='dash')))
    fig.update_layout(xaxis_title="Time", yaxis_title=f"Price ({selected_currency})", hovermode="x unified", margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(eval_df.reset_index(), use_container_width=True)

def render_technical_tab(df_data, tech_score):
    c_left, c_right = st.columns([1, 1])
    with c_left:
        gauge = go.Figure(go.Indicator(
            mode="gauge+number", value=tech_score, title={'text': "Momentum Score"},
            gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "rgba(255,255,255,0.4)"},
                   'steps': [{'range': [0, 35], 'color': "#E74C3C"}, {'range': [35, 65], 'color': "#F1C40F"}, {'range': [65, 100], 'color': "#2ECC71"}]}
        ))
        gauge.update_layout(height=350, margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(gauge, use_container_width=True)
    with c_right:
        st.markdown("<br><br>#### Radar Breakdown", unsafe_allow_html=True)
        st.markdown(f"- **RSI (Relative Strength):** {df_data['RSI_14'].iloc[-1]:.2f}")
        st.markdown(f"- **MACD Trend:** {'Bullish' if df_data['MACD'].iloc[-1] > df_data['MACD_Signal'].iloc[-1] else 'Bearish'}")
        st.markdown(f"- **20-Day Average:** {'Above average' if df_data['Close'].iloc[-1] > df_data['SMA_20'].iloc[-1] else 'Below average'}")

# ==========================================
# MAIN EXECUTION
# ==========================================
inject_custom_css()

if not FIREBASE_AVAILABLE:
    st.error("Firebase is not configured. Missing 'firebase_key.json'.")
    st.stop()

if not enforce_rate_limit():
    st.error("🚦 RATE LIMIT EXCEEDED: Please wait a moment.")
    st.stop()

if not SessionManager.is_logged_in():
    render_auth_gate()

# Sidebar Navigation
st.sidebar.markdown(f"👤 **Account:** `{SessionManager.get_username()}`")
if st.sidebar.button("Log Out", use_container_width=True):
    SessionManager.logout()
    st.rerun()

st.sidebar.markdown("---")
raw_search = st.sidebar.text_input("🔍 Search Market", value=SessionManager.get_ticker())
user_ticker = resolve_ticker(sanitize_ticker(raw_search))
SessionManager.set_ticker(user_ticker)

investment_budget = st.sidebar.number_input("💰 Investment Capital", min_value=10.0, value=1000.0, step=100.0)
selected_currency = st.sidebar.selectbox("🌍 Local Currency", ["USD", "EUR", "GBP", "INR", "JPY", "CAD", "AUD"])
time_interval = st.sidebar.selectbox("🕒 Timeframe", ["1d", "1h", "15m"])

with st.sidebar.expander("⚙️ Advanced AI Settings"):
    start_date = st.date_input("Training Start Date", value=date.today() - timedelta(days=365 * 3))
    look_back = st.slider("Memory Window", 30, 90, 60)
    training_epochs = st.slider("Epochs", 3, 15, 5)

# Main Dashboard
st.markdown('<div class="gradient-header">QuantAI Workspace</div>', unsafe_allow_html=True)

try:
    profile = fetch_company_profile(user_ticker) or {}
    company_name = profile.get('name', user_ticker)
    live_price = profile.get('live_price', 0.0)
    news_data = get_stock_news(user_ticker, company_name)
    df_data = fetch_market_data(user_ticker, start_date, date.today(), interval=time_interval)
    
    if df_data.empty:
        st.error(f"No market data available for '{user_ticker}'.")
        st.stop()

    closes = df_data['Close'].copy()
    min_price_usd = df_data['Low'].min()
    
    try:
        with st.spinner(f"🧠 AI is studying market patterns for {company_name}..."):
            model, targ_scaler = train_and_cache_model(user_ticker, time_interval, look_back, training_epochs)

        # Build Evaluation Data Model
        X, y = [], []
        for i in range(look_back, len(closes)):
            X.append(closes.iloc[i - look_back:i].values)
            y.append(closes.iloc[i])
            
        if not X: raise ValueError("Not enough data for the AI memory window.")
            
        X, y = np.array(X), np.array(y)
        X_flat = X.reshape(X.shape[0], X.shape[1])
        train_len = int(np.ceil(len(X_flat) * TRAIN_TEST_SPLIT))

        with st.spinner("⚡ Forecasting future price..."):
            preds_scaled = model.predict(X_flat[train_len:])
            future_pred_scaled = model.predict(X_flat[-1].reshape(1, -1))

        model_predictions_usd = targ_scaler.inverse_transform(np.array(preds_scaled).reshape(-1, 1)).ravel()
        tomorrow_pred_usd = float(targ_scaler.inverse_transform(np.array(future_pred_scaled).reshape(-1, 1)).ravel()[0])
        rmse_score_usd = np.sqrt(np.mean((model_predictions_usd - y[train_len:]) ** 2)) if len(y[train_len:]) > 0 else 0.0

    except ValueError:
        st.warning("Not enough data for AI model; using simpler persistence forecast for chart.")
        train_len = 1
        model_predictions_usd = closes.shift(1).iloc[train_len:].values
        tomorrow_pred_usd = float(closes.iloc[-1])
        actuals = closes.iloc[train_len:].values
        rmse_score_usd = np.sqrt(np.mean((model_predictions_usd - actuals) ** 2)) if len(actuals) > 0 else 0.0

    # Unified Currency Conversion
    cv_data = apply_currency_conversion({
        'live_price': live_price,
        'tomorrow_pred': tomorrow_pred_usd,
        'rmse_score': rmse_score_usd,
        'min_price': min_price_usd
    }, selected_currency)
    
    tech_score = calculate_technical_score(df_data)

    # Render Components
    render_price_metrics(company_name, profile.get('sector', 'Unknown'), user_ticker, time_interval, df_data, cv_data)
    render_trade_card(cv_data, investment_budget)

    t1, t2, t3, t4 = st.tabs(["📈 AI Forecast", "🧭 Technical Radar", "🗞️ Live News", "ℹ️ Fundamentals"])
    
    with t1: render_forecast_tab(df_data, model_predictions_usd, selected_currency, cv_data)
    with t2: render_technical_tab(df_data, tech_score)
    with t3: display_news(news_data) if news_data else st.info("No recent news found.")
    with t4:
        f1, f2, f3, f4 = st.columns(4)
        f1.metric("Market Cap", format_large_number(profile.get('market_cap')))
        f2.metric("P/E Ratio", profile.get('pe_ratio', 'N/A'))
        f3.metric("52W High", f"${profile.get('high_52', 'N/A')}")
        f4.metric("52W Low", f"${profile.get('low_52', 'N/A')}")
        with st.expander("Read Company Profile"):
            safe_markdown(profile.get('summary', 'No summary available.'))

except Exception as e:
    st.error("An unexpected error occurred during execution.")
    logger.exception("Dashboard rendering failed: %s", e)