import streamlit as st
import pandas as pd
import yfinance as yf
import json
import os
import matplotlib.pyplot as plt

# ----- Persistent Portfolio File -----
PORTFOLIO_FILE = "portfolio.json"

# ----- Load or Initialize Portfolio -----
if os.path.exists(PORTFOLIO_FILE):
    with open(PORTFOLIO_FILE, "r") as f:
        portfolio = json.load(f)
else:
    portfolio = []

# ----- Helper Functions -----
def save_portfolio():
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(portfolio, f, indent=4)

def get_price_on_date(ticker, date):
    data = yf.download(ticker, start=date, end=date, progress=False)
    if data.empty:
        data = yf.download(ticker, start=pd.to_datetime(date) - pd.Timedelta(days=3),
                           end=pd.to_datetime(date) + pd.Timedelta(days=3), progress=False)
    try:
        return round(data["Adj Close"].iloc[0], 2)
    except IndexError:
        return None

def calculate_portfolio_summary(portfolio):
    summary = {}
    for entry in portfolio:
        ticker = entry["ticker"]
        if ticker not in summary:
            summary[ticker] = {
                "total_shares": 0.0,
                "total_cost": 0.0,
                "lots": []
            }
        summary[ticker]["total_shares"] += entry["shares"]
        summary[ticker]["total_cost"] += entry["shares"] * entry["price"]
        summary[ticker]["lots"].append(entry)

    # Add current price and market value
    for ticker in summary:
        current_price = get_price_on_date(ticker, pd.Timestamp.today().strftime("%Y-%m-%d"))
        summary[ticker]["current_price"] = current_price
        summary[ticker]["market_value"] = round(current_price * summary[ticker]["total_shares"], 2) if current_price else 0.0
        summary[ticker]["avg_cost"] = round(summary[ticker]["total_cost"] / summary[ticker]["total_shares"], 2) if summary[ticker]["total_shares"] > 0 else 0.0

    return summary

def plot_portfolio_vs_tickers(portfolio):
    if not portfolio:
        st.info("No purchases to plot yet.")
        return

    df = pd.DataFrame(portfolio)
    df["date"] = pd.to_datetime(df["date"])
    df.sort_values("date", inplace=True)

    start = df["date"].min().strftime("%Y-%m-%d")
    end = pd.Timestamp.today().strftime("%Y-%m-%d")
    compare_with = ["AAPL", "QQQ", "NVDA"]

    # Price download fix for single/multi ticker issue
    price_data_raw = yf.download(compare_with, start=start, end=end, progress=False)
    if isinstance(price_data_raw.columns, pd.MultiIndex):
        price_data = price_data_raw["Adj Close"]
    else:
        price_data = price_data_raw[["Adj Close"]]
        price_data.columns = pd.Index([compare_with[0]])

    # Prepare portfolio growth line
    df["cumulative_cost"] = df["shares"] * df["price"]
    df["cumulative_cost"] = df.groupby("ticker")["cumulative_cost"].cumsum()
    df["cumulative_shares"] = df.groupby("ticker")["shares"].cumsum()

    portfolio_growth = pd.DataFrame(index=price_data.index)
    for ticker in df["ticker"].unique():
        ticker_df = df[df["ticker"] == ticker].copy()
        ticker_df.set_index("date", inplace=True)
        ticker_cost = ticker_df["shares"] * ticker_df["price"]
        ticker_shares = ticker_df["shares"].cumsum()
        purchase_dates = ticker_df.index

        values = []
        total_shares = 0.0
        for date in portfolio_growth.index:
            if date in purchase_dates:
                idx = ticker_df.index.get_loc(date)
                total_shares = ticker_shares.iloc[idx]
            price = price_data[ticker].get(date, None)
            if price and total_shares:
                values.append(total_shares * price)
            else:
                values.append(None)

        portfolio_growth[ticker] = values

    portfolio_growth["Total"] = portfolio_growth.sum(axis=1)

    # Plotting
    st.subheader("📈 Portfolio Growth vs. Major Tickers")
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(portfolio_growth.index, portfolio_growth["Total"], label="Your Portfolio", linewidth=2)
    for ticker in compare_with:
        ax.plot(price_data.index, price_data[ticker] / price_data[ticker].iloc[0] * 10000, linestyle="--", alpha=0.7, label=f"{ticker} (normalized)")
    ax.set_ylabel("Value")
    ax.set_xlabel("Date")
    ax.legend()
    st.pyplot(fig)

# ----- Streamlit UI -----
st.title("💼 Smart DCA Portfolio Tracker")

st.header("Add a New Purchase")
ticker = st.text_input("Ticker (e.g. AAPL)").upper()
date = st.date_input("Purchase Date")
shares = st.number_input("Number of Shares", min_value=0.0, step=0.01)
is_actual = st.checkbox("Count this as actual purchase", value=True)

if st.button("Fetch Price and Add Entry"):
    price = get_price_on_date(ticker, date.strftime("%Y-%m-%d"))
    if price:
        st.success(f"Price on {date}: ${price}")
        if is_actual:
            portfolio.append({
                "ticker": ticker,
                "date": date.strftime("%Y-%m-%d"),
                "shares": shares,
                "price": price
            })
            save_portfolio()
            st.success("Added to portfolio.")
        else:
            st.info("This was only a suggestion. Not saved.")
    else:
        st.error("Could not fetch price.")

# ----- Portfolio Summary -----
st.header("📊 Portfolio Summary")
summary = calculate_portfolio_summary(portfolio)
total_value = 0.0
total_cost = 0.0

for ticker, data in summary.items():
    st.subheader(f"{ticker}")
    st.write(f"Total Shares: {data['total_shares']}")
    st.write(f"Average Cost: ${data['avg_cost']}")
    st.write(f"Current Price: ${data['current_price']}")
    st.write(f"Market Value: ${data['market_value']}")
    st.write(f"Total Cost Basis: ${data['total_cost']}")
    total_value += data["market_value"]
    total_cost += data["total_cost"]

st.markdown(f"### ✅ Total Portfolio Market Value: **${round(total_value, 2)}**")
st.markdown(f"### 💰 Total Cost Basis: **${round(total_cost, 2)}**")
st.markdown(f"### 📈 Net Gain/Loss: **${round(total_value - total_cost, 2)}**")

# ----- Plot Chart -----
plot_portfolio_vs_tickers(portfolio)

# ----- Debug View -----
if st.checkbox("Show raw portfolio data"):
    st.dataframe(pd.DataFrame(portfolio))