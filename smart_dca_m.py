# smart_dca_app.py

import streamlit as st
import pandas as pd
import yfinance as yf
import json
import os
import datetime
import matplotlib.pyplot as plt

st.set_page_config(page_title="Smart DCA Manager", layout="wide")

# 1. Load persistent storage
def load_data():
    if os.path.exists("portfolio.json"):
        with open("portfolio.json", "r") as f:
            return json.load(f)
    else:
        return {"manual_history": [], "suggested_history": []}

def save_data(data):
    with open("portfolio.json", "w") as f:
        json.dump(data, f, indent=4)

state = load_data()
if "manual_history" not in st.session_state:
    st.session_state.manual_history = pd.DataFrame(state["manual_history"])
if "suggested_history" not in st.session_state:
    st.session_state.suggested_history = pd.DataFrame(state["suggested_history"])

# 2. Define helper
def to_dict_list(df):
    return df.to_dict(orient="records") if not df.empty else []

# 3. Load ticker prices
def fetch_price(ticker, date):
    df = yf.download(ticker, start=date, end=date + datetime.timedelta(days=5), progress=False)
    if not df.empty:
        return round(df["Close"][0], 2)
    return None

# 4. Add manual entry
st.header("🧾 Add Manual Purchase")
with st.form("manual_entry"):
    ticker = st.text_input("Ticker", value="QQQ").upper()
    shares = st.number_input("Shares", min_value=0.01, step=0.01)
    date = st.date_input("Date", value=datetime.date.today())
    cost = st.number_input("Total Cost (USD)", min_value=0.01, step=0.01)
    submitted = st.form_submit_button("Add Purchase")
    if submitted:
        st.session_state.manual_history = pd.concat([
            st.session_state.manual_history,
            pd.DataFrame([{
                "Ticker": ticker,
                "Shares": shares,
                "Date": str(date),
                "Cost": cost
            }])
        ], ignore_index=True)
        save_data({
            "manual_history": to_dict_list(st.session_state.manual_history),
            "suggested_history": to_dict_list(st.session_state.suggested_history)
        })
        st.success("Manual purchase added.")

# 5. Show manual history
st.subheader("📘 Manual Purchase History")
if not st.session_state.manual_history.empty:
    st.dataframe(st.session_state.manual_history)
else:
    st.write("No manual purchases yet.")

# 6. Suggested purchase (not counted)
st.header("💡 Suggested Purchase (Not Executed)")
with st.form("suggest_entry"):
    tick = st.text_input("Suggested Ticker", value="AAPL").upper()
    d = st.date_input("Suggestion Date", value=datetime.date.today(), key="sug_date")
    sug_price = fetch_price(tick, d)
    sug_sub = st.form_submit_button("Record Suggestion")
    if sug_sub and sug_price:
        st.session_state.suggested_history = pd.concat([
            st.session_state.suggested_history,
            pd.DataFrame([{
                "Ticker": tick,
                "Date": str(d),
                "Suggested Price": sug_price
            }])
        ], ignore_index=True)
        save_data({
            "manual_history": to_dict_list(st.session_state.manual_history),
            "suggested_history": to_dict_list(st.session_state.suggested_history)
        })
        st.success("Suggestion recorded (not affecting portfolio).")

# 7. Show suggested history
st.subheader("📄 Suggested Purchase Log")
if not st.session_state.suggested_history.empty:
    st.dataframe(st.session_state.suggested_history)
else:
    st.write("No suggestions yet.")

# 8. Portfolio Summary
st.header("📊 Portfolio Summary")
if not st.session_state.manual_history.empty:
    port = st.session_state.manual_history.groupby("Ticker")[["Shares", "Cost"]].sum()
    port["Avg Cost"] = port["Cost"] / port["Shares"]

    prices = {}
    for t in port.index:
        price = fetch_price(t, datetime.date.today())
        if price:
            prices[t] = price
        else:
            prices[t] = 0.0
    port["Price"] = port.index.map(prices)
    port["Value"] = port["Shares"] * port["Price"]
    port["Gain %"] = ((port["Value"] - port["Cost"]) / port["Cost"]) * 100
    st.dataframe(port.style.format({"Avg Cost": ".2f", "Price": ".2f", "Value": ".2f", "Gain %": ".2f"}))
    st.markdown(f"**Total Value:** ${port['Value'].sum():,.2f}")
else:
    st.write("No purchases to summarize.")

# 9. Clear buttons
col1, col2 = st.columns(2)
with col1:
    if st.button("🗑 Clear Manual History"):
        st.session_state.manual_history = pd.DataFrame()
        save_data({
            "manual_history": [],
            "suggested_history": to_dict_list(st.session_state.suggested_history)
        })
        st.experimental_rerun()
with col2:
    if st.button("🗑 Clear Suggested History"):
        st.session_state.suggested_history = pd.DataFrame()
        save_data({
            "manual_history": to_dict_list(st.session_state.manual_history),
            "suggested_history": []
        })
        st.experimental_rerun()

# 10. Download / Upload
st.header("📁 Backup & Restore")
col1, col2 = st.columns(2)
with col1:
    st.download_button("📥 Download Portfolio JSON", data=json.dumps({
        "manual_history": to_dict_list(st.session_state.manual_history),
        "suggested_history": to_dict_list(st.session_state.suggested_history)
    }, indent=4), file_name="portfolio.json")

with col2:
    uploaded = st.file_uploader("📤 Upload portfolio.json", type=["json"])
    if uploaded:
        data = json.load(uploaded)
        st.session_state.manual_history = pd.DataFrame(data.get("manual_history", []))
        st.session_state.suggested_history = pd.DataFrame(data.get("suggested_history", []))
        save_data(data)
        st.success("Portfolio restored.")
        st.experimental_rerun()

# 11. Style
st.markdown("---")
st.markdown("⚙️ **Smart DCA Portfolio Manager** – Developed with ❤️ for tracking real vs suggested investments.")

# 12. Portfolio Growth vs Market Chart
st.header("📈 Portfolio Growth vs Market Comparison")
if not st.session_state.manual_history.empty:
    df = st.session_state.manual_history.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")

    unique_dates = sorted(df["Date"].unique())
    timeline = pd.DataFrame({"Date": unique_dates})
    timeline["Cost Basis"] = [df[df["Date"] <= d]["Cost"].sum() for d in unique_dates]

    # Market value using actual past prices
    timeline["Market Value"] = 0.0
    for i, d in enumerate(unique_dates):
        daily_value = 0
        for _, row in df[df["Date"] <= d].iterrows():
            ticker = row["Ticker"]
            shares = row["Shares"]
            hist_price = fetch_price(ticker, d.date())
            if hist_price:
                daily_value += shares * hist_price
        timeline.at[i, "Market Value"] = daily_value

    st.line_chart(timeline.set_index("Date")[["Cost Basis", "Market Value"]])

    # Comparison lines
    compare_with = ["QQQ", "AAPL", "NVDA"]
    start = df["Date"].min()
    end = datetime.date.today()

    raw_data = yf.download(compare_with, start=start, end=end, progress=False)
    if isinstance(raw_data.columns, pd.MultiIndex):
        price_data = raw_data["Adj Close"]
    else:
        price_data = pd.DataFrame(raw_data["Adj Close"])
        price_data.columns = compare_with

    st.line_chart(price_data)

