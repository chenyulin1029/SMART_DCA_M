# smart_dca_app.py

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import os

# File path for persistent history storage
HISTORY_CSV = "history.csv"

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

def load_history():
    if os.path.exists(HISTORY_CSV):
        try:
            df = pd.read_csv(HISTORY_CSV)
            # ensure columns exist and correct types
            expected_cols = ["Buy Date", "Ticker", "Price", "Shares", "Cost"]
            if all(col in df.columns for col in expected_cols):
                return df[expected_cols]
        except Exception as e:
            st.warning(f"Failed to load history file: {e}")
    # fallback empty
    return pd.DataFrame(columns=["Buy Date", "Ticker", "Price", "Shares", "Cost"])

def save_history(df):
    df.to_csv(HISTORY_CSV, index=False)

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

    price = prices[candidate]
    shares = np.floor(invest_amt / price * 1000) / 1000
    cost = shares * price

    return {
        "Buy Ticker": candidate,
        "Price": price,
        "Shares": shares,
        "Cost": cost,
        "Suggested Rotation": rotation
    }

# 4. UI Layout
st.title("📊 Smart DCA Investment Engine")

ticker_str = st.text_input("Enter Tickers (comma-separated)", value="QQQ,AAPL,NVDA")
preset = st.radio("Choose Investment Preset", ['$450 (Default)', '$600 (Future)'])
custom_amt = st.number_input("Or enter custom amount", min_value=0.0, max_value=5000.0, step=10.0, value=0.0)
amount = 450 if (custom_amt == 0 and preset == '$450 (Default)') else (600 if custom_amt == 0 else custom_amt)

cutoff_date = st.date_input("Cutoff Date", value=get_last_trade_and_buy_dates()[1])
buy_date = st.date_input("Buy Date", value=get_last_trade_and_buy_dates()[2])

st.markdown("### Rotation Counts (Input your current rotation state for suggestion)")
col1, col2, col3 = st.columns(3)
count_qqq = col1.number_input("QQQ", min_value=0, max_value=3, value=0)
count_aapl = col2.number_input("AAPL", min_value=0, max_value=3, value=0)
count_nvda = col3.number_input("NVDA", min_value=0, max_value=3, value=3)

# 5. Load persistent history on start
if 'history' not in st.session_state:
    st.session_state.history = load_history()

# 6. Run DCA Suggestion ONLY (no save)
if st.button("Run Smart DCA Suggestion"):
    try:
        tickers = validate_tickers(ticker_str)
        init_counts = {'QQQ': count_qqq, 'AAPL': count_aapl, 'NVDA': count_nvda}
        result = run_dca(tickers, init_counts, cutoff_date, buy_date, amount)

        st.success("✅ Smart DCA Suggestion:")
        st.write(result)

    except Exception as e:
        st.error(f"❌ {e}")

# 7. Manual Buy Entry Form (only way to add to history)
st.markdown("### ✍️ Manually Add Buy Record")
with st.form("manual_entry"):
    col1, col2 = st.columns(2)
    m_ticker = col1.text_input("Ticker", value="AAPL").upper()
    m_date = col2.date_input("Buy Date", value=datetime.date.today())

    col3, col4 = st.columns(2)
    m_qty = col3.number_input("Quantity", min_value=0.0, step=0.1)
    m_price = col4.number_input("Buy Price", min_value=0.0, step=0.1)

    submitted = st.form_submit_button("➕ Add Buy Record")
    if submitted:
        if m_ticker not in valid_tickers:
            st.warning(f"Ticker `{m_ticker}` is not valid or not in S&P 500 list.")
        else:
            row = {
                "Buy Date": str(m_date),
                "Ticker": m_ticker,
                "Price": m_price,
                "Shares": m_qty,
                "Cost": m_qty * m_price
            }
            st.session_state.history = pd.concat([st.session_state.history, pd.DataFrame([row])], ignore_index=True)
            save_history(st.session_state.history)
            st.success("✅ Entry added!")

# 8. Show Buy History Table with delete and edit support
st.markdown("### 📜 Purchase History")

def edit_history():
    df = st.session_state.history.copy()
    edited = False

    for i, row in df.iterrows():
        with st.expander(f"Edit Record {i+1}: {row['Ticker']} on {row['Buy Date']}"):
            col1, col2, col3, col4, col5 = st.columns(5)
            new_date = col1.date_input("Buy Date", pd.to_datetime(row['Buy Date']))
            new_ticker = col2.text_input("Ticker", row['Ticker']).upper()
            new_price = col3.number_input("Price", value=float(row['Price']), min_value=0.0, step=0.01, format="%.2f")
            new_shares = col4.number_input("Shares", value=float(row['Shares']), min_value=0.0, step=0.001, format="%.3f")
            new_cost = col5.number_input("Cost", value=float(row['Cost']), min_value=0.0, step=0.01, format="%.2f", disabled=True)

            # Recalculate cost if price or shares changed
            if new_price != row['Price'] or new_shares != row['Shares']:
                new_cost = new_price * new_shares

            if st.button(f"Save Changes #{i+1}"):
                if new_ticker not in valid_tickers:
                    st.warning(f"Ticker `{new_ticker}` is not valid or not in S&P 500 list.")
                else:
                    df.at[i, 'Buy Date'] = str(new_date)
                    df.at[i, 'Ticker'] = new_ticker
                    df.at[i, 'Price'] = new_price
                    df.at[i, 'Shares'] = new_shares
                    df.at[i, 'Cost'] = new_cost
                    st.session_state.history = df
                    save_history(df)
                    st.experimental_rerun()  # refresh to show updates

            if st.button(f"Delete Record #{i+1}"):
                df = df.drop(i).reset_index(drop=True)
                st.session_state.history = df
                save_history(df)
                st.experimental_rerun()

    if df.empty:
        st.info("No purchase history yet.")

edit_history()

# 9. Chart: Pie of Allocation by Cost
st.markdown("### 🧩 Allocation by Cost")
if not st.session_state.history.empty:
    pie_data = st.session_state.history.groupby("Ticker")["Cost"].sum()
    st.pyplot(pie_data.plot.pie(autopct='%1.1f%%', figsize=(5, 5), ylabel="").get_figure())

# 10. Chart: Cumulative Investment Over Time
st.markdown("### 📈 Cumulative Investment Over Time")
if not st.session_state.history.empty:
    df = st.session_state.history.copy()
    df["Buy Date"] = pd.to_datetime(df["Buy Date"])
    df = df.sort_values("Buy Date")
    df["Cumulative Cost"] = df["Cost"].cumsum()
    st.line_chart(df.set_index("Buy Date")["Cumulative Cost"])

# 11. Portfolio Summary based on manual history + live price
st.markdown("### 📊 Portfolio Summary")
if not st.session_state.history.empty:
    try:
        tickers = st.session_state.history["Ticker"].unique().tolist()
        # yf.download can return MultiIndex columns, handle that:
        price_df = yf.download(tickers=tickers, period="1d", progress=False)
        if 'Adj Close' in price_df.columns:
            latest_prices = price_df['Adj Close'].iloc[-1].to_dict()
        elif isinstance(price_df.columns, pd.MultiIndex):
            # Some tickers, pick 'Adj Close' level
            latest_prices = {}
            for t in tickers:
                try:
                    latest_prices[t] = price_df['Adj Close'][t].iloc[-1]
                except Exception:
                    latest_prices[t] = np.nan
        else:
            # fallback to Close
            latest_prices = price_df.iloc[-1].to_dict()

        df = st.session_state.history.copy()
        df["Current Price"] = df["Ticker"].map(latest_prices)
        df["Current Value"] = df["Shares"] * df["Current Price"]
        df["Gain"] = df["Current Value"] - df["Cost"]
        df["Gain %"] = (df["Gain"] / df["Cost"]) * 100

        st.dataframe(df[["Ticker", "Buy Date", "Shares", "Price", "Cost", "Current Price", "Current Value", "Gain", "Gain %"]].round(2))

        col1, col2, col3 = st.columns(3)
        total_cost = df["Cost"].sum()
        total_value = df["Current Value"].sum()
        gain = total_value - total_cost
        gain_pct = (gain / total_cost) * 100 if total_cost > 0 else 0

        col1.metric("💰 Invested", f"${total_cost:,.2f}")
        col2.metric("📈 Value Now", f"${total_value:,.2f}")
        col3.metric("📊 Gain/Loss", f"${gain:,.2f}", delta=f"{gain_pct:.2f}%")
    except Exception as e:
        st.warning(f"📉 Could not load current prices: {e}")
