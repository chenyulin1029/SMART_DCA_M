import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime

st.set_page_config(page_title="Smart DCA Tracker", layout="centered")
st.title("📊 Smart DCA – Editable Buy History with Real-Time Gain/Loss")

# --- Initialize session state ---
if "buy_history" not in st.session_state:
    st.session_state.buy_history = pd.DataFrame(columns=["Ticker", "Buy Date", "Quantity", "Buy Price"])

# --- Editable Buy History ---
st.subheader("📋 Edit Your Buy History")

edited_df = st.data_editor(
    st.session_state.buy_history,
    num_rows="dynamic",
    use_container_width=True,
    key="buy_history_editor"
)

# Save edited data back to session
st.session_state.buy_history = edited_df

# --- Helper: Fetch current prices ---
@st.cache_data(ttl=300)
def fetch_current_prices(tickers):
    data = yf.download(tickers=tickers, period="1d", progress=False, threads=True)
    if len(tickers) == 1:
        return {tickers[0]: data["Adj Close"][-1]}
    else:
        return {ticker: data["Adj Close"][ticker][-1] for ticker in tickers}

# --- Validate & Calculate Portfolio Summary ---
def compute_summary(df):
    df = df.dropna()
    if df.empty:
        return pd.DataFrame(), 0, 0

    df["Buy Date"] = pd.to_datetime(df["Buy Date"]).dt.date
    tickers = df["Ticker"].str.upper().unique().tolist()

    try:
        current_prices = fetch_current_prices(tickers)
    except Exception as e:
        st.error("⚠️ Failed to fetch prices. Try again later.")
        return pd.DataFrame(), 0, 0

    df["Ticker"] = df["Ticker"].str.upper()
    df["Current Price"] = df["Ticker"].map(current_prices)
    df["Total Cost"] = df["Quantity"] * df["Buy Price"]
    df["Current Value"] = df["Quantity"] * df["Current Price"]
    df["Gain/Loss"] = df["Current Value"] - df["Total Cost"]
    df["Gain %"] = (df["Gain/Loss"] / df["Total Cost"]) * 100

    total_cost = df["Total Cost"].sum()
    total_value = df["Current Value"].sum()
    return df, total_cost, total_value

# --- Portfolio Summary ---
st.subheader("📈 Real-Time Portfolio Summary")

summary_df, total_cost, total_value = compute_summary(st.session_state.buy_history)

if not summary_df.empty:
    st.dataframe(summary_df.round(2), use_container_width=True)

    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    col1.metric("💰 Total Cost", f"${total_cost:,.2f}")
    col2.metric("📈 Current Value", f"${total_value:,.2f}")
    col3.metric("📊 Gain/Loss", f"${total_value - total_cost:,.2f}", delta=f"{((total_value - total_cost)/total_cost)*100:.2f}%" if total_cost > 0 else "0.00%")

else:
    st.info("Please enter some buy history data to view your portfolio summary.")


