# smart_dca_app.py

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import json
import os

# 1. Load tickers
@st.cache_data
def load_valid_tickers():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    table = pd.read_html(url)[0]
    return set(table['Symbol'].tolist() + ['QQQ', 'NVDA'])

valid_tickers = load_valid_tickers()

# 2. Utility functions
def fetch_price(ticker, date):
    df = yf.download(ticker, start=date - datetime.timedelta(days=200),
                     end=date + datetime.timedelta(days=1),
                     progress=False, auto_adjust=False)
    col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
    return float(df[col].loc[:pd.to_datetime(date)].iloc[-1])

def get_current_price(ticker):
    df = yf.download(ticker, period="2d", interval="1d", progress=False, auto_adjust=False)
    col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
    return float(df[col].iloc[-1]) if not df.empty else 0.0

def validate_tickers(input_str):
    tickers = [t.strip().upper() for t in input_str.split(',') if t.strip()]
    invalid = [t for t in tickers if t not in valid_tickers]
    if invalid:
        raise ValueError(f"Invalid tickers: {invalid}")
    return tickers

def get_last_trade_and_buy_dates():
    today = datetime.date.today()
    offset = 1 if today.weekday() >= 5 else 0
    last_trade = today - datetime.timedelta(days=offset)
    tentative = datetime.date(today.year, today.month, 15)
    while tentative.weekday() >= 5:
        tentative += datetime.timedelta(days=1)
    return today, last_trade, tentative

# 3. Smart DCA logic
def run_dca(tickers, init_counts, cutoff_date, buy_date, invest_amt):
    prices = {t: fetch_price(t, cutoff_date) for t in tickers}
    raw = {}
    for t in tickers:
        p0 = prices[t]
        p1 = fetch_price(t, cutoff_date - datetime.timedelta(days=30))
        p3 = fetch_price(t, cutoff_date - datetime.timedelta(days=90))
        p6 = fetch_price(t, cutoff_date - datetime.timedelta(days=180))
        r1, r3, r6 = p0 / p1 - 1, p0 / p3 - 1, p0 / p6 - 1
        raw[t] = 0.2*r1 + 0.3*r3 + 0.5*r6

    rotation = init_counts.copy()
    sorted_raw = sorted(raw.items(), key=lambda x: x[1], reverse=True)

    for t, score in sorted_raw:
        if rotation.get(t, 0) < 3:
            candidate = t
            break
    else:
        candidate = sorted_raw[0][0]
        for t in rotation:
            rotation[t] = 0

    rotation[candidate] += 1
    for t in rotation:
        if t != candidate:
            rotation[t] = 0

    price = prices[candidate]
    shares = np.floor(invest_amt / price * 1000) / 1000
    cost = shares * price

    return {
        "Buy Ticker": candidate,
        "Price": price,
        "Shares": shares,
        "Cost": cost,
        "New Rotation": rotation
    }

# --- Persistence helper functions ---
PORTFOLIO_FILE = "portfolio.json"

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r") as f:
                data = json.load(f)
            df = pd.DataFrame(data)
            expected_cols = ["Buy Date", "Ticker", "Price", "Shares", "Cost"]
            for col in expected_cols:
                if col not in df.columns:
                    df[col] = np.nan
            return df[expected_cols]
        except Exception:
            return pd.DataFrame(columns=["Buy Date", "Ticker", "Price", "Shares", "Cost"])
    else:
        return pd.DataFrame(columns=["Buy Date", "Ticker", "Price", "Shares", "Cost"])

def save_portfolio(df):
    df_to_save = df.copy()
    df_to_save["Buy Date"] = df_to_save["Buy Date"].astype(str)
    df_to_save["Ticker"] = df_to_save["Ticker"].astype(str)
    df_to_save["Price"] = df_to_save["Price"].astype(float)
    df_to_save["Shares"] = df_to_save["Shares"].astype(float)
    df_to_save["Cost"] = df_to_save["Cost"].astype(float)
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(df_to_save.to_dict(orient="records"), f, indent=2)

# 4. UI Layout
st.title("📊 Smart DCA Investment Engine")

ticker_str = st.text_input("Enter Tickers (comma-separated)", value="QQQ,AAPL,NVDA")
preset = st.radio("Choose Investment Preset", ['$450 (Default)', '$600 (Future)'])
custom_amt = st.number_input("Or enter custom amount", min_value=0.0, max_value=5000.0, step=10.0, value=0.0)
amount = 450 if (custom_amt == 0 and preset == '$450 (Default)') else (600 if custom_amt == 0 else custom_amt)

cutoff_date = st.date_input("Cutoff Date", value=get_last_trade_and_buy_dates()[1])
buy_date = st.date_input("Buy Date", value=get_last_trade_and_buy_dates()[2])

st.markdown("### Rotation Counts")
col1, col2, col3 = st.columns(3)
count_qqq = col1.number_input("QQQ", min_value=0, max_value=3, value=0)
count_aapl = col2.number_input("AAPL", min_value=0, max_value=3, value=0)
count_nvda = col3.number_input("NVDA", min_value=0, max_value=3, value=3)

# 5. Session State Init & Load Portfolio
if "portfolio" not in st.session_state:
    st.session_state.portfolio = load_portfolio()
if "rotation" not in st.session_state:
    st.session_state.rotation = {"QQQ": 0, "AAPL": 0, "NVDA": 0}

# 6. Run DCA
if st.button("Suggest via Smart DCA"):
    try:
        tickers = validate_tickers(ticker_str)
        init_counts = {'QQQ': count_qqq, 'AAPL': count_aapl, 'NVDA': count_nvda}
        result = run_dca(tickers, init_counts, cutoff_date, buy_date, amount)
        st.success("✅ Smart DCA Suggestion:")
        st.write(result)
    except Exception as e:
        st.error(f"❌ {e}")

# 7. Manual Entry
st.markdown("### ➕ Manually Add Purchase")
with st.form("manual_entry"):
    manual_date = st.date_input("Buy Date (Manual)", value=datetime.date.today())
    manual_ticker = st.selectbox("Ticker", sorted(valid_tickers))
    manual_price = st.number_input("Buy Price", min_value=0.01, step=0.01)
    manual_shares = st.number_input("Shares", min_value=0.001, step=0.001)
    submitted = st.form_submit_button("Add Purchase")
    if submitted:
        cost = manual_price * manual_shares
        new_row = {
            "Buy Date": str(manual_date),
            "Ticker": manual_ticker,
            "Price": manual_price,
            "Shares": manual_shares,
            "Cost": cost
        }
        st.session_state.portfolio = pd.concat([st.session_state.portfolio, pd.DataFrame([new_row])], ignore_index=True)
        save_portfolio(st.session_state.portfolio)
        st.success("Purchase added and saved.")

# 8. Show Portfolio
st.markdown("### 📜 Your Investment Portfolio")
if not st.session_state.portfolio.empty:
    edited_df = st.data_editor(st.session_state.portfolio, num_rows="dynamic", use_container_width=True)
    if not edited_df.equals(st.session_state.portfolio):
        st.session_state.portfolio = edited_df.reset_index(drop=True)
        save_portfolio(st.session_state.portfolio)
        st.success("Portfolio updated and saved.")
    with st.expander("🗑️ Delete a Row"):
        index_to_delete = st.number_input("Row index to delete", min_value=0, max_value=len(st.session_state.portfolio)-1, step=1)
        if st.button("Delete Selected Row"):
            st.session_state.portfolio = st.session_state.portfolio.drop(index_to_delete).reset_index(drop=True)
            save_portfolio(st.session_state.portfolio)
            st.success("Row deleted and portfolio saved.")
else:
    st.info("No portfolio data available. Please add purchases.")

# 9. Summary
st.markdown("### 📦 Portfolio Summary with Gain/Loss")
if not st.session_state.portfolio.empty:
    df = st.session_state.portfolio.copy()
    tickers = df["Ticker"].unique()
    current_prices = {t: get_current_price(t) for t in tickers}
    df["Current Price"] = df["Ticker"].map(current_prices)
    df["Current Value"] = df["Current Price"] * df["Shares"]
    summary = df.groupby("Ticker").agg(
        Total_Shares=("Shares", "sum"),
        Total_Cost=("Cost", "sum"),
        Current_Price=("Current Price", "mean"),
        Current_Value=("Current Value", "sum")
    )
    summary["Gain/Loss"] = summary["Current_Value"] - summary["Total_Cost"]
    st.dataframe(summary.style.format({
        "Total_Cost": "${:.2f}",
        "Current_Price": "${:.2f}",
        "Current_Value": "${:.2f}",
        "Gain/Loss": "${:.2f}"
    }), use_container_width=True)
else:
    st.info("No portfolio data to summarize.")

# 10. Allocation Pie
st.markdown("### 🧩 Allocation by Cost")
if not st.session_state.portfolio.empty:
    pie_data = st.session_state.portfolio.groupby("Ticker")["Cost"].sum()
    st.pyplot(pie_data.plot.pie(autopct='%1.1f%%', figsize=(5, 5), ylabel="").get_figure())
else:
    st.info("No portfolio data to display allocation.")

# 11. Cumulative Investment Chart
st.markdown("### 📈 Cumulative Investment Over Time")
if not st.session_state.portfolio.empty:
    df = st.session_state.portfolio.copy()
    df["Buy Date"] = pd.to_datetime(df["Buy Date"])
    df = df.sort_values("Buy Date")
    df["Cumulative Cost"] = df["Cost"].cumsum()
    st.line_chart(df.set_index("Buy Date")["Cumulative Cost"])
else:
    st.info("No portfolio data to display cumulative investment.")
