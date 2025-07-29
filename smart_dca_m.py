import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="📈 Smart DCA Tracker", layout="wide")

# ------------------------------
# 🎯 INIT
# ------------------------------
if "history" not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=["Buy Date", "Ticker", "Price", "Shares", "Cost"])
if "rotation" not in st.session_state:
    st.session_state.rotation = {"AAPL": 0, "QQQ": 0, "NVDA": 0}

tickers = ["AAPL", "QQQ", "NVDA"]
base_budget = 450  # You can allow the user to customize this later

# ------------------------------
# 🧠 SMART DCA SUGGESTION ENGINE
# ------------------------------
def smart_dca(buy_date):
    try:
        prices = {ticker: yf.Ticker(ticker).history(start=buy_date, end=buy_date).iloc[0]["Close"] for ticker in tickers}
    except Exception as e:
        st.error(f"❌ Failed to fetch prices for {buy_date}. Check ticker or network.")
        return None

    # Exclude tickers that have been bought 3 times
    eligible = {k: v for k, v in st.session_state.rotation.items() if v < 3}
    if not eligible:
        st.warning("🔁 Rotation completed. All tickers bought 3 times. Resetting rotation.")
        st.session_state.rotation = {k: 0 for k in tickers}
        eligible = st.session_state.rotation

    # Choose ticker with lowest momentum count (or default to NVDA in tie)
    sorted_tickers = sorted(eligible.items(), key=lambda x: (x[1], -prices[x[0]]))
    buy_ticker = sorted_tickers[0][0]
    price = prices[buy_ticker]
    shares = round(base_budget / price, 4)
    cost = round(shares * price, 2)

    new_rotation = st.session_state.rotation.copy()
    new_rotation[buy_ticker] += 1

    return {
        "Buy Ticker": buy_ticker,
        "Price": round(price, 2),
        "Shares": shares,
        "Cost": cost,
        "New Rotation": new_rotation
    }

# ------------------------------
# 📅 USER DATE INPUT
# ------------------------------
st.title("📊 Smart DCA Portfolio Tracker")

with st.expander("🧠 Smart DCA Monthly Suggestion"):
    buy_date = st.date_input("Select Buy Date", value=datetime.today())
    if st.button("💡 Suggest Buy"):
        result = smart_dca(str(buy_date))
        if result:
            st.session_state.rotation = result["New Rotation"]
            st.success("✅ Smart DCA Suggestion:")
            st.write({
                "Buy Date": str(buy_date),
                "Ticker": result["Buy Ticker"],
                "Price": result["Price"],
                "Shares": result["Shares"],
                "Cost": result["Cost"]
            })

# ------------------------------
# ✍️ MANUAL RECORD ENTRY
# ------------------------------
with st.expander("✍️ Manually Add Buy Record"):
    manual_date = st.date_input("Buy Date")
    manual_ticker = st.selectbox("Ticker", tickers)
    manual_price = st.number_input("Price", min_value=0.0, value=100.0)
    manual_shares = st.number_input("Shares", min_value=0.0, value=1.0)
    if st.button("➕ Add to History"):
        manual_cost = round(manual_price * manual_shares, 2)
        new_row = {
            "Buy Date": str(manual_date),
            "Ticker": manual_ticker,
            "Price": manual_price,
            "Shares": manual_shares,
            "Cost": manual_cost
        }
        st.session_state.history = pd.concat([st.session_state.history, pd.DataFrame([new_row])], ignore_index=True)
        st.success("✅ Record added!")

# ------------------------------
# 📂 PURCHASE HISTORY DISPLAY
# ------------------------------
st.subheader("📜 Purchase History")
if not st.session_state.history.empty:
    st.dataframe(st.session_state.history, use_container_width=True)
else:
    st.info("No buy history yet.")

# ------------------------------
# 📊 PIE CHART & SUMMARY
# ------------------------------
st.subheader("📈 Portfolio Allocation Overview")
if not st.session_state.history.empty:
    pie_data = st.session_state.history.groupby("Ticker")["Cost"].sum()
    try:
        fig = pie_data.plot.pie(autopct='%1.1f%%', figsize=(5, 5), ylabel="").get_figure()
        st.pyplot(fig)
    except ImportError:
        st.warning("Pie chart requires matplotlib. Please install it locally.")
else:
    st.info("Buy history required to generate chart.")

# ------------------------------
# 🔁 ROTATION TRACKING
# ------------------------------
st.sidebar.subheader("🔄 Current Rotation Count")
st.sidebar.write(st.session_state.rotation)

# ------------------------------
# 🧹 RESET
# ------------------------------
with st.sidebar.expander("⚠️ Reset Options"):
    if st.button("🔁 Reset Rotation"):
        st.session_state.rotation = {ticker: 0 for ticker in tickers}
        st.success("Rotation reset!")
    if st.button("🗑️ Clear History"):
        st.session_state.history = pd.DataFrame(columns=["Buy Date", "Ticker", "Price", "Shares", "Cost"])
        st.success("History cleared!")
