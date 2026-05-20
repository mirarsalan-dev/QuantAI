import time
import threading
import streamlit as st
import hashlib
from streamlit.runtime.scriptrunner import get_script_run_ctx

# --- FIREBASE CLOUD IMPORTS (Fast) ---
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore import FieldFilter

# ==========================================
# PAGE CONFIGURATION (Must be first)
# ==========================================
st.set_page_config(page_title="QuantAI Suite", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 🛡️ SECURITY: DUAL-LAYER RATE LIMITER (Auth-Exempt)
# ==========================================
@st.cache_resource
def get_rate_limiter():
    return {'global_hits': [], 'session_hits': {}, 'lock': threading.Lock()}

def enforce_rate_limit(max_requests=30, time_window=60.0):
    # EXEMPTION: Do not limit users who are not yet authenticated (prevents login lockouts)
    if not st.session_state.get('logged_in', False):
        return True
        
    store = get_rate_limiter()
    ctx = get_script_run_ctx()
    session_id = ctx.session_id if ctx else "headless_bot"
    now = time.time()
    
    with store['lock']:
        valid_global = [ts for ts in store['global_hits'] if now - ts < time_window]
        if session_id not in store['session_hits']: store['session_hits'][session_id] = []
        valid_session = [ts for ts in store['session_hits'][session_id] if now - ts < time_window]
        
        if len(valid_global) >= max_requests or len(valid_session) >= max_requests:
            return False
            
        store['global_hits'] = valid_global + [now]
        store['session_hits'][session_id] = valid_session + [now]
        return True

# Apply the limit ONLY if the user is logged in
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


# ==========================================
# CLOUD DATABASE SETUP
# ==========================================
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate('firebase_key.json')
        firebase_admin.initialize_app(cred)
    except Exception:
        st.error("⚠️ Could not find 'firebase_key.json'.")

db = firestore.client()

def hash_password(password): return hashlib.sha256(str.encode(password)).hexdigest()

def create_user(username, password):
    doc_ref = db.collection('users').document(username)
    if doc_ref.get().exists: return False
    doc_ref.set({'password': hash_password(password), 'created_at': firestore.SERVER_TIMESTAMP})
    return True

def login_user(username, password):
    doc_ref = db.collection('users').document(username)
    doc = doc_ref.get()
    if doc.exists and doc.to_dict().get('password') == hash_password(password): return True
    return False

# ==========================================
# UI ROUTING: HARD AUTHENTICATION GATE
# ==========================================
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.markdown('<style>[data-testid="stSidebar"] { display: none; }</style>', unsafe_allow_html=True)
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.container(border=True):
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
                    else: st.error("Access Denied.")
            else:
                new_user_input = st.text_input("Choose Username", key="reg_user")
                new_pass_input = st.text_input("Choose Password", type="password", key="reg_pass")
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Initialize Secure Profile", type="secondary", use_container_width=True):
                    if len(new_user_input) < 3 or len(new_pass_input) < 4: st.warning("Username: 3+ chars. Password: 4+ chars.")
                    elif create_user(new_user_input, new_pass_input): st.success("Created! Switch to 'Sign In'.")
                    else: st.error("Username already exists.")
                    
    # EVERYTHING STOPS HERE IF NOT LOGGED IN!
    st.stop()


# ==========================================
# 🚀 LAZY-LOADING HEAVY LIBRARIES 
# ==========================================
import requests
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import date, timedelta
from sklearn.preprocessing import MinMaxScaler

# ==========================================
# CLOUD HISTORY FUNCTIONS
# ==========================================
def save_search(username, ticker):
    history_ref = db.collection('history')
    query = history_ref.where(filter=FieldFilter('username', '==', username)).where(filter=FieldFilter('ticker', '==', ticker)).limit(1).get()
    if not query: history_ref.add({'username': username, 'ticker': ticker, 'timestamp': firestore.SERVER_TIMESTAMP})

def get_search_history(username):
    try:
        query = db.collection('history').where(filter=FieldFilter('username', '==', username)).order_by('timestamp', direction=firestore.Query.DESCENDING).get()
        return [doc.to_dict().get('ticker') for doc in query]
    except Exception:
        query = db.collection('history').where(filter=FieldFilter('username', '==', username)).get()
        return [doc.to_dict().get('ticker') for doc in query]

# ==========================================
# FAST-CACHED FINANCIAL FUNCTIONS
# ==========================================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_company_profile(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        try: live_price = t.fast_info['lastPrice']
        except: live_price = 0.0
        return {
            'name': info.get('longName', ticker), 'sector': info.get('sector', 'Unknown'),
            'summary': info.get('longBusinessSummary', 'No summary available.'),
            'market_cap': info.get('marketCap', 'N/A'), 'pe_ratio': info.get('trailingPE', 'N/A'),
            'high_52': info.get('fiftyTwoWeekHigh', 'N/A'), 'low_52': info.get('fiftyTwoWeekLow', 'N/A'),
            'live_price': live_price
        }
    except Exception: return None

@st.cache_resource
def load_ai_frameworks():
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import Dense, LSTM, Dropout, Input, Bidirectional
    return Sequential, Dense, LSTM, Dropout, Input, Bidirectional

@st.cache_data(ttl=86400, show_spinner=False)
def resolve_ticker(query):
    if not query: return "AAPL"
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=5).json()
        if 'quotes' in response and len(response['quotes']) > 0:
            for quote in response['quotes']:
                if quote.get('quoteType') in ['EQUITY', 'ETF', 'MUTUALFUND']: return quote['symbol']
            return response['quotes'][0]['symbol']
    except Exception: pass
    return query.upper()

@st.cache_data(ttl=300, show_spinner=False)
def load_and_process_data(ticker, start, end, interval="1d"):
    period = "59d" if interval == "15m" else "729d" if interval == "1h" else None
    if period: df = yf.download(ticker, period=period, interval=interval)
    else: df = yf.download(ticker, start=start, end=end, interval=interval)
        
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    data = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
    data['SMA_20'] = data['Close'].rolling(window=20).mean()
    std_20 = data['Close'].rolling(window=20).std()
    data['Bollinger_Upper'] = data['SMA_20'] + (std_20 * 2)
    data['Bollinger_Lower'] = data['SMA_20'] - (std_20 * 2)
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    data['RSI_14'] = 100 - (100 / (1 + gain / (loss + 1e-9)))
    ema_12 = data['Close'].ewm(span=12, adjust=False).mean()
    ema_26 = data['Close'].ewm(span=26, adjust=False).mean()
    data['MACD'] = ema_12 - ema_26
    data['MACD_Signal'] = data['MACD'].ewm(span=9, adjust=False).mean()
    data['EMA_50'] = data['Close'].ewm(span=50, adjust=False).mean()
    return data.dropna()

@st.cache_resource(ttl=86400, show_spinner=False)
def train_and_cache_model(ticker, interval, look_back_days, epochs):
    Sequential, Dense, LSTM, Dropout, Input, Bidirectional = load_ai_frameworks()
    df = load_and_process_data(ticker, date.today() - timedelta(days=729), date.today(), interval=interval)
    feat_scaler, targ_scaler = MinMaxScaler((0,1)), MinMaxScaler((0,1))
    scaled_feats = feat_scaler.fit_transform(df.values)
    scaled_targs = targ_scaler.fit_transform(df[['Close']].values)
    x_train = np.array([scaled_feats[i-look_back_days:i, :] for i in range(look_back_days, len(scaled_feats))])
    y_train = np.array([scaled_targs[i, 0] for i in range(look_back_days, len(scaled_feats))])
    
    model = Sequential([
        Input(shape=(x_train.shape[1], x_train.shape[2])),
        Bidirectional(LSTM(64, return_sequences=True)), Dropout(0.2),
        LSTM(32, return_sequences=False), Dense(1)
    ])
    model.compile(optimizer='adam', loss='huber')
    model.fit(x_train, y_train, batch_size=64, epochs=epochs, verbose=0)
    return model, feat_scaler, targ_scaler

@st.cache_data(ttl=3600, show_spinner=False)
def get_exchange_rate(target_currency):
    if target_currency == "USD": return 1.0, "$"
    symbols = {"EUR": "€", "GBP": "£", "INR": "₹", "JPY": "¥", "CAD": "C$", "AUD": "A$"}
    try: return yf.Ticker(f"USD{target_currency}=X").fast_info['lastPrice'], symbols.get(target_currency, target_currency+" ")
    except: return 1.0, "$"

@st.cache_data(ttl=1800, show_spinner=False)
def get_stock_news(ticker, company_name):
    query = f"{ticker}+stock" if ticker else company_name.replace(' ', '+')
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    try:
        import xml.etree.ElementTree as ET
        resp = requests.get(url, timeout=5)
        root = ET.fromstring(resp.text)
        items = root.findall(".//item")
        news_list = []
        for item in items[:6]:
            title = item.find("title").text if item.find("title") is not None else "Headline Unavailable"
            link = item.find("link").text if item.find("link") is not None else "#"
            source = item.find("source").text if item.find("source") is not None else "Financial Press"
            if " - " in title: title = title.rsplit(" - ", 1)[0]
            news_list.append({'title': title, 'link': link, 'publisher': source})
        return news_list
    except Exception: return []

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

# --- SIDEBAR ---
st.sidebar.markdown(f"👤 **Account:** `{st.session_state['username']}`")
if st.sidebar.button("Log Out", type="secondary", use_container_width=True):
    st.session_state.clear()
    st.rerun()
st.sidebar.markdown("---")

st.sidebar.markdown("### 🔍 Search Market")
raw_search = st.sidebar.text_input("Company Name or Symbol", value=st.session_state.get('active_ticker', "AAPL"))
user_ticker = resolve_ticker(raw_search)
st.session_state['active_ticker'] = user_ticker
save_search(st.session_state['username'], user_ticker)

st.sidebar.markdown("### 💰 Portfolio Setup")
investment_budget = st.sidebar.number_input("Investment Capital", min_value=10.0, value=1000.0, step=100.0)

st.sidebar.markdown("### 🌍 Display Options")
selected_currency = st.sidebar.selectbox("Local Currency", ["USD", "EUR", "GBP", "INR", "JPY", "CAD", "AUD"])
time_interval = st.sidebar.selectbox("Timeframe", options=["1d", "1h", "15m"], format_func=lambda x: "Long Term (Daily)" if x=="1d" else "Day Trading (Hourly)" if x=="1h" else "Scalping (15-Minute)", help="Choose the candle interval.")

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
    with st.spinner(f"🧠 AI is studying market patterns for {company_name}..."):
        model, feat_scaler, targ_scaler = train_and_cache_model(user_ticker, time_interval, look_back, training_epochs)

    df_data = load_and_process_data(user_ticker, start_date, date.today(), interval=time_interval)
    feature_data = df_data.values
    target_data = df_data[['Close']].values
    train_len = int(np.ceil(len(feature_data) * .85))
    scaled_feats = feat_scaler.transform(feature_data)
    
    with st.spinner("⚡ Forecasting future price..."):
        x_test = np.array([scaled_feats[i-look_back:i, :] for i in range(train_len, len(scaled_feats))])
        X_future = np.array([scaled_feats[-look_back:]])
        preds_scaled = model.predict(x_test, verbose=0)
        future_pred_scaled = model.predict(X_future, verbose=0)
    
    model_predictions_usd = targ_scaler.inverse_transform(preds_scaled)
    tomorrow_pred_usd = targ_scaler.inverse_transform(future_pred_scaled)[0][0]
    rmse_score_usd = np.sqrt(np.mean(((model_predictions_usd - target_data[train_len:]) ** 2)))
    
    min_timeframe_price_usd = df_data['Low'].min()
    
    fx_rate, fx_sym = get_exchange_rate(selected_currency)
    live_price_cv = live_price * fx_rate
    tomorrow_pred_cv = tomorrow_pred_usd * fx_rate
    rmse_score_cv = rmse_score_usd * fx_rate
    min_price_cv = min_timeframe_price_usd * fx_rate 
    
    # --- TECHNICAL SENTIMENT ---
    tech_score = 50
    if df_data['RSI_14'].iloc[-1] < 40: tech_score += 25
    elif df_data['RSI_14'].iloc[-1] > 60: tech_score -= 25
    if df_data['MACD'].iloc[-1] > df_data['MACD_Signal'].iloc[-1]: tech_score += 15
    else: tech_score -= 15
    if df_data['Close'].iloc[-1] > df_data['SMA_20'].iloc[-1]: tech_score += 10
    else: tech_score -= 10
    tech_score = max(0, min(100, tech_score))
    
    # --- HEADER ---
    st.markdown(f"### 🏢 {company_name} (`{user_ticker}`)")
    st.caption(f"**Industry:** {sector} | **AI Timeframe:** {time_interval}")
    
    m1, m2, m3, m4 = st.columns(4)
    dir_text = "🟢 BULLISH" if tomorrow_pred_usd > df_data['Close'].iloc[-1] else "🔴 BEARISH"
    
    m1.metric(f"Current Live Price ({selected_currency})", f"{fx_sym}{live_price_cv:.2f}" if live_price > 0 else "Closed")
    m2.metric("AI Forecast", f"{fx_sym}{tomorrow_pred_cv:.2f}", f"Trend: {dir_text}")
    m3.metric("Minimum Price", f"{fx_sym}{min_price_cv:.2f}")
    m4.metric("AI Error Margin", f"± {fx_sym}{rmse_score_cv:.2f}")
        
    # --- AI TRADE CARD ---
    if live_price > 0:
        afford = investment_budget / live_price_cv
        pnl_amt = (afford * tomorrow_pred_cv) - investment_budget
        pnl_pct = (pnl_amt / investment_budget) * 100
        stop_loss = live_price_cv - rmse_score_cv
        
        r_text, r_col = ("🟢 BUY RECOMMENDED", "#2ECC71") if pnl_pct > 0.5 else ("🔴 AVOID / SELL", "#E74C3C") if pnl_pct < -0.5 else ("🟡 NEUTRAL / HOLD", "#F1C40F")

        st.markdown(f"""
            <div style="background: var(--secondary-background-color); padding: 20px; border-radius: 12px; border-left: 6px solid {r_col}; margin: 15px 0 25px 0; border-top: 1px solid rgba(128,128,128,0.2); border-right: 1px solid rgba(128,128,128,0.2); border-bottom: 1px solid rgba(128,128,128,0.2); box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                <h4 style="margin-top:0px; color:{r_col}; font-weight: 800;">{r_text}</h4>
                <p style="margin-bottom:8px; font-size:1.1rem;">Budget <b>{fx_sym}{investment_budget:,.2f}</b> = <b>{afford:,.4f} shares</b>.</p>
                <p style="margin-bottom:0px; font-size:1.1rem;">Projected PnL: <b style="color:{r_col};">{fx_sym}{pnl_amt:+,.2f} ({pnl_pct:+,.2f}%)</b>. AI Stop-Loss calculated at: <b>{fx_sym}{stop_loss:,.2f}</b>.</p>
            </div>
        """, unsafe_allow_html=True)

    # --- TABS ---
    t1, t2, t3, t4 = st.tabs(["📈 AI Forecast", "🧭 Technical Radar", "🗞️ Live News", "ℹ️ Company & Data"])
    
    with t1:
        eval_df = df_data[train_len:].copy()
        eval_df['Close_Cv'] = df_data['Close'][train_len:] * fx_rate
        eval_df['Preds_Cv'] = model_predictions_usd * fx_rate
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=eval_df.index, y=eval_df['Close_Cv'], name="Market Price", line=dict(color='#2ECC71', width=2)))
        fig.add_trace(go.Scatter(x=eval_df.index, y=eval_df['Preds_Cv'], name="AI Prediction", line=dict(color='#8B5CF6', dash='dash')))
        fig.update_layout(xaxis_title="Time", yaxis_title=f"Price ({selected_currency})", hovermode="x unified", margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig, use_container_width=True, theme="streamlit")
        
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
            st.markdown(f"- **RSI (Relative Strength):** {df_data['RSI_14'].iloc[-1]:.2f} *(Below 30 is Oversold, Above 70 is Overbought)*")
            st.markdown(f"- **MACD Trend:** {'Bullish (Above Signal)' if df_data['MACD'].iloc[-1] > df_data['MACD_Signal'].iloc[-1] else 'Bearish (Below Signal)'}")
            st.markdown(f"- **20-Day Average:** {'Price is holding above average' if df_data['Close'].iloc[-1] > df_data['SMA_20'].iloc[-1] else 'Price crashed below average'}")

    with t3:
        st.markdown("### Latest Market Headlines")
        if not news_data: st.info("No recent news found for this asset right now.")
        else:
            for article in news_data:
                st.markdown(f"""
                <div class="news-card">
                    <a href="{article.get('link', '#')}" target="_blank">{article.get('title', 'Headline Unavailable')}</a>
                    <div class="news-publisher">Published by {article.get('publisher', 'Financial Press')}</div>
                </div>
                """, unsafe_allow_html=True)
                
    with t4:
        st.markdown("### Fundamental Statistics")
        f1, f2, f3, f4 = st.columns(4)
        f1.metric("Market Cap", f"{format_large_number(market_cap)}")
        f2.metric("P/E Ratio", f"{pe_ratio}")
        f3.metric("52-Week High", f"${high_52}")
        f4.metric("52-Week Low", f"${low_52}")
        
        with st.expander("Read Company Profile"): st.write(summary)
        st.markdown("---")
        
        c1, c2 = st.columns([3,1])
        c1.markdown("### Raw Market Data Matrices")
        csv_data = df_data.tail(100).to_csv().encode('utf-8')
        c2.download_button(label="💾 Download Data (CSV)", data=csv_data, file_name=f"{user_ticker}_quant_data.csv", mime="text/csv", use_container_width=True)
        st.dataframe(df_data[['Close', 'Volume', 'SMA_20', 'RSI_14', 'MACD']].tail(30), use_container_width=True)

except Exception as e:
    st.error("⚠️ The AI encountered an error reading data for this asset. Try searching for a different company.")
    with st.expander("Technical Error"): st.exception(e)