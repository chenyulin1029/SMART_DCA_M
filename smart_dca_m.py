import streamlit as st
import pandas as pd
import yfinance as yf
import json
import os

DATA_FILE = "portfolio.json"

# Load persistent portfolio data
def load_portfolio():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return []

# Save updated portfolio
def save_portfolio(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# Fetch current price using yfinance
@st.cache_data(ttl=3600)
def get_current_price(ticker):
    try:
        data = yf.download(ticker, period="1d")
        return round(data["Adj Close"].iloc[-1], 2)
    except:
        return 0.0

# Calculate portfolio summary
def generate_summary(portfolio):
    summary = []
    total_cost = 0
    total_value = 0

    for entry in portfolio:
        ticker = entry["ticker"]
        shares = float(entry["shares"])
        cost = float(entry["cost"])
        buy_price = float(entry["buy_price"])
        current_price = get_current_price(ticker)
        current_value = shares * current_price
        gain = current_value - cost

        summary.append({
            "Ticker": ticker,
            "Buy Date": entry["buy_date"],
            "Shares": round(shares, 5),
            "Buy Price": buy_price,
            "Current Price": current_price,
            "Cost": round(cost, 2),
            "Current Value": round(current_value, 2),
            "Unrealized Gain": round(gain, 2)
        })

        total_cost += cost
        total_value += current_value

    df = pd.DataFrame(summary)
    totals = {
        "Total Cost": round(total_cost, 2),
        "Total Value": round(total_value, 2),
        "Total Gain": round(total_value - total_cost, 2)
    }

    return df, totals

# App UI
st.set_page_config(page_title="Smart DCA Portfolio Tracker", layout="wide")
st.title("📊 Smart DCA Portfolio Tracker")

portfolio = load_portfolio()

tab1, tab2 = st.tabs(["💼 Portfolio Summary", "➕ Manual Purchase Entry"])

with tab1:
    df, totals = generate_summary(portfolio)
    if not df.empty:
        st.dataframe(df, use_container_width=True)
        st.subheader("📈 Portfolio Totals")
        st.metric("Total Invested", f"${totals['Total Cost']}")
        st.metric("Current Value", f"${totals['Total Value']}")
        st.metric("Unrealized Gain", f"${totals['Total Gain']}")
    else:
        st.info("No portfolio data found.")

    st.subheader("🧹 Edit or Delete Entries")
    if portfolio:
        selected = st.selectbox("Select an entry to edit or delete", options=[f"{p['ticker']} | {p['buy_date']} | {p['shares']} shares" for p in portfolio])
        idx = [f"{p['ticker']} | {p['buy_date']} | {p['shares']} shares" for p in portfolio].index(selected)
        entry = portfolio[idx]
        new_ticker = st.text_input("Ticker", entry["ticker"])
        new_date = st.text_input("Buy Date", entry["buy_date"])
        new_shares = st.number_input("Shares", value=float(entry["shares"]), format="%.5f")
        new_price = st.number_input("Buy Price", value=float(entry["buy_price"]))
        new_cost = st.number_input("Cost", value=float(entry["cost"]))

        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Save Changes"):
                portfolio[idx] = {
                    "ticker": new_ticker.upper(),
                    "buy_date": new_date,
                    "shares": new_shares,
                    "buy_price": new_price,
                    "cost": new_cost
                }
                save_portfolio(portfolio)
                st.success("Entry updated. Please refresh.")
        with col2:
            if st.button("🗑️ Delete Entry"):
                portfolio.pop(idx)
                save_portfolio(portfolio)
                st.warning("Entry deleted. Please refresh.")

with tab2:
    st.subheader("Add a New Manual Purchase")
    ticker = st.text_input("Ticker (e.g., QQQ, AAPL)").upper()
    buy_date = st.date_input("Buy Date")
    shares = st.number_input("Shares Purchased", format="%.5f")
    buy_price = st.number_input("Buy Price per Share")
    cost = st.number_input("Total Cost")

    if st.button("➕ Add Purchase"):
        new_entry = {
            "ticker": ticker,
            "buy_date": str(buy_date),
            "shares": shares,
            "buy_price": buy_price,
            "cost": cost
        }
        portfolio.append(new_entry)
        save_portfolio(portfolio)
        st.success(f"{ticker} purchase added.")

