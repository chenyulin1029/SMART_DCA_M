import streamlit as st
import pandas as pd
import yfinance as yf
import datetime
from collections import defaultdict

st.set_page_config(page_title="Smart DCA Tracker", layout="wide")

# --------- 1. Init ----------
st.title("📈 Smart DCA Portfolio Tracker")
st.markdown("Track your Smart DCA progress with real-time charts and manual inputs.")

# --------- 2. Session State ---------
if "history" not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=["Buy Date", "Ticker", "Price", "Shares", "Cost"])

# --------- 3. Utilities ---------
@st.cache_data
def fetch_price(ticker, date):
    try:
        data = yf.download(ticker, start=date - datetime.timedelta(days=5), end=date + datetime.timedelta(days=5), progress=False)
        if date.strftime("%Y-%m-%d") in data.index.strftime("%Y-%m-%d"):
            return float(data.loc[date.strftime("%Y-%m-%d")]["Close"])
        else:
            return float(data["Close"][-1])
    except Exception as e:
        st.warning(f"⚠️ Error fetching price for {ticker} on {date}: {e}")
        return None

def get_latest_price(ticker):
    try:
        data = yf.Ticker(ticker).history(period="5d")
        return float(data["Close"][-1])
    except:
        return None

# --------- 4. Portfolio Summary ---------
st.markdown("### 💼 Portfolio Overview")

if st.session_state.history.empty:
    st.info("No buy records yet. Add a record manually below or use Smart DCA logic.")
else:
    df = st.session_state.history.copy()
    df["Buy Date"] = pd.to_datetime(df["Buy Date"])
    df["Total Cost"] = df["Price"] * df["Shares"]

    # Group by Ticker
    grouped = df.groupby("Ticker").agg({
        "Shares": "sum",
        "Total Cost": "sum"
    })

    # Get current prices
    grouped["Current Price"] = grouped.index.to_series().apply(get_latest_price)
    grouped["Current Value"] = grouped["Shares"] * grouped["Current Price"]
    grouped["Gain %"] = ((grouped["Current Value"] - grouped["Total Cost"]) / grouped["Total Cost"]) * 100
    grouped["Gain %"] = grouped["Gain %"].round(2)

    st.dataframe(grouped[["Shares", "Total Cost", "Current Price", "Current Value", "Gain %"]])

# --------- 5. Charts ---------
if not st.session_state.history.empty:
    st.markdown("### 📊 Portfolio Allocation")

    pie_data = st.session_state.history.groupby("Ticker")["Cost"].sum()
    fig = pie_data.plot.pie(autopct='%1.1f%%', figsize=(5, 5), ylabel="").get_figure()
    st.pyplot(fig)

# --------- 5.1 Manual Buy Entry (Enhanced) ---------
st.markdown("### ✍️ Manually Add Buy Record")
with st.form("manual_entry"):
    col1, col2 = st.columns(2)
    m_ticker = col1.text_input("Ticker", value="AAPL").upper()
    m_date = col2.date_input("Buy Date", value=datetime.date.today())

    col3, col4 = st.columns(2)
    m_qty = col3.number_input("Quantity", min_value=0.0, step=0.1, format="%.4f")
    m_price = col4.number_input("Buy Price", min_value=0.0, step=0.1, format="%.2f")

    submitted = st.form_submit_button("➕ Add Buy Record")
    if submitted:
        if m_qty <= 0 or m_price <= 0:
            st.warning("🚫 Quantity and Price must be greater than 0.")
        else:
            row = {
                "Buy Date": str(m_date),
                "Ticker": m_ticker,
                "Price": m_price,
                "Shares": m_qty,
                "Cost": m_qty * m_price
            }
            st.session_state.history = pd.concat([st.session_state.history, pd.DataFrame([row])], ignore_index=True)
            st.success(f"✅ Added manual entry: {m_qty} shares of {m_ticker} at ${m_price:.2f}")

# --------- 6. Smart DCA Buy Entry ---------
st.markdown("### 🤖 Smart DCA Buy Simulation (Optional)")
with st.expander("Run Smart DCA Buy (Example Logic)", expanded=False):
    tickers = ["AAPL", "QQQ", "NVDA"]
    dca_amt = st.number_input("Monthly DCA Amount", min_value=0, value=450, step=50)
    dca_date = st.date_input("Buy Date", value=datetime.date.today())

    if st.button("Run Smart DCA Buy"):
        per_ticker_amt = dca_amt / len(tickers)
        rows = []
        for ticker in tickers:
            price = fetch_price(ticker, dca_date)
            if price:
                shares = per_ticker_amt / price
                row = {
                    "Buy Date": str(dca_date),
                    "Ticker": ticker,
                    "Price": price,
                    "Shares": shares,
                    "Cost": shares * price
                }
                rows.append(row)

        if rows:
            st.session_state.history = pd.concat([st.session_state.history, pd.DataFrame(rows)], ignore_index=True)
            st.success(f"✅ Smart DCA buy for {len(rows)} assets added.")

# --------- 7. Reset ---------
st.markdown("### ⚙️ Settings")
if st.button("🧹 Clear All Buy History"):
    st.session_state.history = pd.DataFrame(columns=["Buy Date", "Ticker", "Price", "Shares", "Cost"])
    st.success("Buy history cleared.")
