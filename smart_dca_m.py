# smart_dca_app.py

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import json
import urllib.parse

# -----------------------------------------------
# 0. Query-param persistence (per-tab isolation)
# -----------------------------------------------

def load_portfolio() -> pd.DataFrame:
    """Load portfolio from the URL query-param 'portfolio' (JSON-encoded)."""
    raw = st.query_params.get("portfolio", ["[]"])[0]
    try:
        records = json.loads(urllib.parse.unquote(raw))
        df = pd.DataFrame(records)
        for col in ["Buy Date","Ticker","Price","Shares","Cost"]:
            if col not in df.columns:
                df[col] = np.nan
        return df[["Buy Date","Ticker","Price","Shares","Cost"]]
    except Exception:
        return pd.DataFrame(columns=["Buy Date","Ticker","Price","Shares","Cost"])

def save_portfolio(df: pd.DataFrame):
    """Save portfolio back into the URL query-param 'portfolio'."""
    records = df.to_dict(orient="records")
    encoded = urllib.parse.quote(json.dumps(records))
    st.experimental_set_query_params(portfolio=encoded)

# -----------------------------------------------
# 1. Load tickers
# -----------------------------------------------

@st.cache_data
def load_valid_tickers():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    table = pd.read_html(url)[0]
    return set(table['Symbol'].tolist() + ['QQQ', 'NVDA'])

valid_tickers = load_valid_tickers()

# -----------------------------------------------
# 2. Utility functions
# -----------------------------------------------

def fetch_price(ticker, date):
    df = yf.download(
        ticker,
        start=date - datetime.timedelta(days=200),
        end=date + datetime.timedelta(days=1),
        progress=False,
        auto_adjust=False
    )
    col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
    return float(df[col].loc[:pd.to_datetime(date)].iloc[-1])

def get_current_price(ticker):
    df = yf.download(
        ticker,
        period="2d", interval="1d",
        progress=False, auto_adjust=False
    )
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

# -----------------------------------------------
# 3. Smart DCA logic
# -----------------------------------------------

def run_dca(tickers, init_counts, cutoff_date, buy_date, invest_amt):
    prices = {t: fetch_price(t, cutoff_date) for t in tickers}
    raw = {}
    for t in tickers:
        p0 = prices[t]
        p1 = fetch_price(t, cutoff_date - datetime.timedelta(days=30))
        p3 = fetch_price(t, cutoff_date - datetime.timedelta(days=90))
        p6 = fetch_price(t, cutoff_date - datetime.timedelta(days=180))
        r1, r3, r6 = p0/p1 - 1, p0/p3 - 1, p0/p6 - 1
        raw[t] = 0.2*r1 + 0.3*r3 + 0.5*r6

    rotation = init_counts.copy()
    sorted_raw = sorted(raw.items(), key=lambda x: x[1], reverse=True)

    for t, _ in sorted_raw:
        if rotation.get(t, 0) < 3:
            candidate = t
            break
    else:
        candidate = sorted_raw[0][0]
        for k in rotation:
            rotation[k] = 0

    rotation[candidate] += 1
    for k in rotation:
        if k != candidate:
            rotation[k] = 0

    price  = prices[candidate]
    shares = np.floor(invest_amt / price * 1000) / 1000
    cost   = shares * price

    return {
        "Buy Ticker": candidate,
        "Price":      price,
        "Shares":     shares,
        "Cost":       cost,
        "New Rotation": rotation
    }

# -----------------------------------------------
# 4. UI Layout
# -----------------------------------------------

st.title("📊 Smart DCA Investment Engine")

# 4.1 Smart-DCA ticker picker
if "rotation" not in st.session_state:
    st.session_state.rotation = {}

ticker_str = st.text_input("Enter Tickers (comma-separated)", value="QQQ,AAPL,NVDA")
st.markdown("#### Or pick tickers from the universe")
ticker_list = st.multiselect(
    "Select Tickers",
    options=sorted(valid_tickers),
    default=["QQQ","AAPL","NVDA"]
)
tickers_to_use = ticker_list or [t.strip().upper() for t in ticker_str.split(",") if t.strip()]

preset     = st.radio("Choose Preset", ["$450 (Default)","$600 (Future)"])
custom_amt = st.number_input("Or enter custom amount", 0.0, 5000.0, 0.0, step=10.0)
amount     = 450 if (custom_amt==0 and preset=="$450 (Default)") else (600 if custom_amt==0 else custom_amt)

cutoff_date = st.date_input("Cutoff Date", value=get_last_trade_and_buy_dates()[1])
buy_date    = st.date_input("Buy Date",   value=get_last_trade_and_buy_dates()[2])

st.markdown("### Rotation Counts")
cols = st.columns(len(tickers_to_use))
init_counts = {}
for i, t in enumerate(tickers_to_use):
    default_ct = st.session_state.rotation.get(t,0)
    init_counts[t] = cols[i].number_input(f"{t} Count", 0, 3, default_ct)

# -----------------------------------------------
# 5. Load portfolio (from URL)
# -----------------------------------------------
if "portfolio" not in st.session_state:
    st.session_state.portfolio = load_portfolio()

# -----------------------------------------------
# 6. Run DCA (suggestion only)
# -----------------------------------------------
if st.button("Suggest via Smart DCA"):
    try:
        tickers = validate_tickers(",".join(tickers_to_use))
        res     = run_dca(tickers, init_counts, cutoff_date, buy_date, amount)
        st.success("✅ Smart DCA Suggestion:")
        st.write(res)
        # … you can re-insert your momentum breakdown & chart here …
    except Exception as e:
        st.error(f"❌ {e}")

# -----------------------------------------------
# 7. Manual Entry
# -----------------------------------------------
st.markdown("### ➕ Manually Add Purchase")
with st.form("manual_entry"):
    md = st.date_input("Buy Date", value=datetime.date.today())
    mt = st.selectbox("Ticker", sorted(valid_tickers))
    mp = st.number_input("Buy Price", min_value=0.01, step=0.01)
    ms = st.number_input("Shares",    min_value=0.001, step=0.001)
    if st.form_submit_button("Add Purchase"):
        cost = mp * ms
        nr = {"Buy Date":str(md),"Ticker":mt,"Price":mp,"Shares":ms,"Cost":cost}
        st.session_state.portfolio = pd.concat(
            [st.session_state.portfolio, pd.DataFrame([nr])],
            ignore_index=True
        )
        save_portfolio(st.session_state.portfolio)
        st.success("Added & saved.")

# -----------------------------------------------
# 8. Show & Edit Portfolio
# -----------------------------------------------
st.markdown("### 📜 Your Investment Portfolio")
if not st.session_state.portfolio.empty:
    key = f"editor_{len(st.session_state.portfolio)}"
    edited = st.data_editor(
        st.session_state.portfolio,
        num_rows="dynamic",
        use_container_width=True,
        key=key
    )
    if not edited.equals(st.session_state.portfolio):
        st.session_state.portfolio = edited.reset_index(drop=True)
        save_portfolio(st.session_state.portfolio)
        st.success("Portfolio updated & saved.")

    with st.expander("🗑️ Delete a Row"):
        opts = [
            (i, f"{i}: {r.Ticker} on {r['Buy Date']} — {r.Shares} shares")
            for i, r in st.session_state.portfolio.iterrows()
        ]
        idxs, labels = zip(*opts)
        to_del = st.selectbox("Select row to delete", options=idxs, format_func=lambda i: labels[idxs.index(i)])
        if st.button("Delete Selected Row"):
            st.session_state.portfolio = (
                st.session_state.portfolio.drop(to_del).reset_index(drop=True)
            )
            save_portfolio(st.session_state.portfolio)
            st.success(f"Deleted row {to_del}.")
else:
    st.info("No portfolio data — please add purchases above.")

# -----------------------------------------------
# 9. Summary
# -----------------------------------------------
st.markdown("### 📦 Portfolio Summary with Gain/Loss")
if st.session_state.portfolio.empty:
    st.info("No data to summarize.")
else:
    df = st.session_state.portfolio.copy()
    tickers = df["Ticker"].unique()
    prices  = {t: get_current_price(t) for t in tickers}
    df["Current Price"] = df["Ticker"].map(prices)
    df["Current Value"] = df["Current Price"] * df["Shares"]
    summary = df.groupby("Ticker").agg(
        Total_Shares=("Shares","sum"),
        Total_Cost=("Cost","sum"),
        Current_Price=("Current Price","mean"),
        Current_Value=("Current Value","sum"),
    )
    summary["Gain/Loss"] = summary["Current_Value"] - summary["Total_Cost"]
    st.dataframe(
        summary.style.format({
            "Total_Cost":"${:.2f}",
            "Current_Price":"${:.2f}",
            "Current_Value":"${:.2f}",
            "Gain/Loss":"${:.2f}"
        }),
        use_container_width=True
    )

# -----------------------------------------------
# 10. Allocation by Cost (Altair Pie)
# -----------------------------------------------
import altair as alt

st.markdown("### 🧩 Allocation by Cost")
if st.session_state.portfolio.empty:
    st.info("No data to show allocation.")
else:
    port = (
        st.session_state.portfolio
        .groupby("Ticker")["Cost"]
        .sum()
        .reset_index(name="Total Cost")
    )
    pie = (
        alt.Chart(port)
        .mark_arc(innerRadius=50, stroke="#fff")
        .encode(
            theta=alt.Theta("Total Cost:Q"),
            color=alt.Color("Ticker:N", legend=alt.Legend(title="Ticker")),
            tooltip=[alt.Tooltip("Ticker:N"), alt.Tooltip("Total Cost:Q",format="$,.2f")]
        )
        .properties(width=400, height=400)
    )
    st.altair_chart(pie, use_container_width=True)

# -----------------------------------------------
# 11. Cumulative Investment Over Time + Value
# -----------------------------------------------
st.markdown("### 📈 Cumulative Investment & Current Value Over Time")
if st.session_state.portfolio.empty:
    st.info("No data to chart.")
else:
    df = st.session_state.portfolio.copy()
    df["Buy Date"] = pd.to_datetime(df["Buy Date"])
    df = df.sort_values("Buy Date")
    df["Cumulative Cost"]  = df["Cost"].cumsum()
    tickers = df["Ticker"].unique().tolist()
    curr_pr  = {t: get_current_price(t) for t in tickers}
    cum_vals = []
    units    = {}
    for _,row in df.iterrows():
        units.setdefault(row["Ticker"],0.0)
        units[row["Ticker"]] += row["Shares"]
        cum_vals.append(sum(units[t]*curr_pr[t] for t in units))
    df["Cumulative Value"] = cum_vals
    chart_df = df.set_index("Buy Date")[["Cumulative Cost","Cumulative Value"]]
    st.line_chart(chart_df)
    total_c = df["Cost"].sum()
    total_v = cum_vals[-1] if cum_vals else 0.0
    gain    = total_v - total_c
    pct     = (gain/total_c*100) if total_c else 0
    c1,c2,c3 = st.columns(3)
    c1.metric("💰 Invested",  f"${total_c:,.2f}")
    c2.metric("📈 Value Now", f"${total_v:,.2f}")
    c3.metric("📊 Gain/Loss", f"${gain:,.2f}", delta=f"{pct:.2f}%")

