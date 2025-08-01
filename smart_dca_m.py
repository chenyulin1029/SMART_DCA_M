# smart_dca_app.py

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import json
import os
import uuid

# -----------------------------------------------
# 0. Per-session user_id for file isolation
# -----------------------------------------------
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())
SESSION_FILE = f"portfolio_{st.session_state.user_id}.json"
GLOBAL_FILE  = "portfolio.json"

# -----------------------------------------------
# 1. Load tickers
# -----------------------------------------------
@st.cache_data
def load_valid_tickers():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    table = pd.read_html(url)[0]
    return set(table['Symbol'].tolist() + ['QQQ', 'NVDA', 'MSFT'])
valid_tickers = load_valid_tickers()

# -----------------------------------------------
# 2. Utility functions
# -----------------------------------------------
def fetch_price(ticker, date):
    df = yf.download(
        ticker,
        start=date - datetime.timedelta(days=200),
        end=date + datetime.timedelta(days=1),
        progress=False, auto_adjust=False
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
    raw    = {}
    for t in tickers:
        p0 = prices[t]
        p1 = fetch_price(t, cutoff_date - datetime.timedelta(days=30))
        p3 = fetch_price(t, cutoff_date - datetime.timedelta(days=90))
        p6 = fetch_price(t, cutoff_date - datetime.timedelta(days=180))
        r1, r3, r6 = p0/p1 - 1, p0/p3 - 1, p0/p6 - 1
        raw[t] = 0.2*r1 + 0.3*r3 + 0.5*r6

    rotation   = init_counts.copy()
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
        "Buy Ticker":   candidate,
        "Price":        price,
        "Shares":       shares,
        "Cost":         cost,
        "New Rotation": rotation
    }

# -----------------------------------------------
# 4. Persistence helpers
# -----------------------------------------------
def load_portfolio():
    # seed session file from global if needed
    if os.path.exists(GLOBAL_FILE) and not os.path.exists(SESSION_FILE):
        try:
            with open(GLOBAL_FILE) as gf:
                data = json.load(gf)
            with open(SESSION_FILE, "w") as sf:
                json.dump(data, sf, indent=2)
        except:
            pass

    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE) as sf:
                data = json.load(sf)
            df = pd.DataFrame(data)
            for col in ["Buy Date","Ticker","Price","Shares","Cost"]:
                if col not in df.columns:
                    df[col] = np.nan
            return df[["Buy Date","Ticker","Price","Shares","Cost"]]
        except:
            pass

    return pd.DataFrame(columns=["Buy Date","Ticker","Price","Shares","Cost"])

def save_portfolio(df):
    df2 = df.copy()
    df2["Buy Date"] = df2["Buy Date"].astype(str)
    df2["Ticker"]   = df2["Ticker"].astype(str)
    df2["Price"]    = df2["Price"].astype(float)
    df2["Shares"]   = df2["Shares"].astype(float)
    df2["Cost"]     = df2["Cost"].astype(float)
    with open(SESSION_FILE, "w") as sf:
        json.dump(df2.to_dict(orient="records"), sf, indent=2)

# -----------------------------------------------
# 5. UI Layout
# -----------------------------------------------
st.title("📊 Smart DCA Investment Engine")

# ticker entry + multiselect fallback
ticker_str = st.text_input("Enter Tickers (comma-separated)", value="QQQ,NVDA,MSFT")
st.markdown("#### Or pick tickers from the universe")
ticker_list = st.multiselect(
    "Select Tickers",
    options=sorted(valid_tickers),
    default=["QQQ","NVDA","MSFT"]
)
tickers_to_use = ticker_list if ticker_list else [
    t.strip().upper() for t in ticker_str.split(",") if t.strip()
]

# amount controls
preset     = st.radio("Choose Preset", ["$450 (Default)", "$600 (Future)"])
custom_amt = st.number_input("Or enter custom amount",
                             min_value=0.0, max_value=5000.0,
                             step=10.0, value=0.0)
amount     = 450 if (custom_amt==0 and preset=="$450 (Default)") else \
             (600 if custom_amt==0 else custom_amt)

cutoff_date = st.date_input("Cutoff Date", value=get_last_trade_and_buy_dates()[1])
buy_date    = st.date_input("Buy Date",   value=get_last_trade_and_buy_dates()[2])

# rotation counts
st.markdown("### Rotation Counts")
if "rotation" not in st.session_state:
    st.session_state.rotation = {}
cols = st.columns(len(tickers_to_use))
init_counts = {}
for i, t in enumerate(tickers_to_use):
    default_ct    = st.session_state.rotation.get(t, 0)
    init_counts[t] = cols[i].number_input(f"{t} Count", 0, 3, default_ct)

# load portfolio into session
if "portfolio" not in st.session_state:
    st.session_state.portfolio = load_portfolio()

# -----------------------------------------------
# 6. Suggest via Smart DCA (no data mutation)
# -----------------------------------------------
if st.button("Suggest via Smart DCA", key="suggest_button"):
    try:
        tickers = validate_tickers(",".join(tickers_to_use))
        res     = run_dca(tickers, init_counts, cutoff_date, buy_date, amount)
        st.success("✅ Suggestion:")
        st.write(res)
    except Exception as e:
        st.error(f"❌ {e}")

# -----------------------------------------------
# 7. Manual Entry
# -----------------------------------------------
st.markdown("### ➕ Manually Add Purchase")
with st.form("manual_entry_form", clear_on_submit=True):
    md = st.date_input("Buy Date (Manual)", value=datetime.date.today())
    mt = st.selectbox("Ticker", sorted(valid_tickers))
    mp = st.number_input("Buy Price", min_value=0.01, step=0.01)
    ms = st.number_input("Shares", min_value=0.001, step=0.001)
    submitted = st.form_submit_button("Add Purchase")

if submitted:
    cost = mp * ms
    new_row = {
        "Buy Date": str(md),
        "Ticker":   mt,
        "Price":    mp,
        "Shares":   ms,
        "Cost":     cost
    }
    st.session_state.portfolio = pd.concat(
        [st.session_state.portfolio, pd.DataFrame([new_row])],
        ignore_index=True
    )
    save_portfolio(st.session_state.portfolio)
    st.success("✅ Purchase added and saved.")

# -----------------------------------------------
# 8. Show / Edit / Delete Portfolio
# -----------------------------------------------
st.markdown("### 📜 Your Investment Portfolio")
if not st.session_state.portfolio.empty:
    editor_key = f"editor_{len(st.session_state.portfolio)}"
    edited_df  = st.data_editor(
        st.session_state.portfolio,
        num_rows="dynamic",
        use_container_width=True,
        key=editor_key
    )
    if not edited_df.equals(st.session_state.portfolio):
        st.session_state.portfolio = edited_df.reset_index(drop=True)
        save_portfolio(st.session_state.portfolio)
        st.success("✅ Portfolio updated & saved.")

    with st.expander("🗑️ Delete a Row"):
        opts = [
            (i, f"{i}: {r.Ticker} on {r['Buy Date']} — {r.Shares} shares")
            for i, r in st.session_state.portfolio.iterrows()
        ]
        idxs, labels = zip(*opts)
        to_del = st.selectbox(
            "Select row to delete",
            options=idxs,
            format_func=lambda i: labels[idxs.index(i)]
        )
        if st.button("Delete Selected Row", key="del_row"):
            st.session_state.portfolio = (
                st.session_state.portfolio
                  .drop(to_del)
                  .reset_index(drop=True)
            )
            save_portfolio(st.session_state.portfolio)
            st.success(f"✅ Row {to_del} deleted & saved.")
else:
    st.info("No portfolio data—please add purchases above.")

# -----------------------------------------------
# 9. Portfolio Summary
# -----------------------------------------------
st.markdown("### 📦 Portfolio Summary with Gain/Loss")
if not st.session_state.portfolio.empty:
    df = st.session_state.portfolio.copy()
    tickers = df["Ticker"].unique()
    current_prices = {t: get_current_price(t) for t in tickers}
    df["Current Price"] = df["Ticker"].map(current_prices)
    df["Current Value"] = df["Current Price"] * df["Shares"]
    summary = df.groupby("Ticker").agg(
        Total_Shares   = ("Shares", "sum"),
        Total_Cost     = ("Cost",   "sum"),
        Current_Price  = ("Current Price", "mean"),
        Current_Value  = ("Current Value", "sum")
    )
    summary["Gain/Loss"] = summary["Current_Value"] - summary["Total_Cost"]
    st.dataframe(summary.style.format({
        "Total_Cost":    "${:.2f}",
        "Current_Price": "${:.2f}",
        "Current_Value": "${:.2f}",
        "Gain/Loss":     "${:.2f}"
    }), use_container_width=True)
else:
    st.info("No portfolio data to summarize.")

# -----------------------------------------------
# 10. Allocation Pie (Altair)
# -----------------------------------------------
import altair as alt
st.markdown("### 🧩 Allocation by Cost")
if not st.session_state.portfolio.empty:
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
             tooltip=[
               alt.Tooltip("Ticker:N"),
               alt.Tooltip("Total Cost:Q", format="$,.2f")
             ]
         )
         .properties(width=400, height=400)
    )
    st.altair_chart(pie, use_container_width=True)
else:
    st.info("No portfolio data to display allocation.")

# -----------------------------------------------
# 11. Cumulative Investment Over Time
# -----------------------------------------------
st.markdown("### 📈 Cumulative Investment & Current Value Over Time")
if not st.session_state.portfolio.empty:
    df = st.session_state.portfolio.copy()
    df["Buy Date"]    = pd.to_datetime(df["Buy Date"])
    df = df.sort_values("Buy Date")
    df["Cumulative Cost"] = df["Cost"].cumsum()

    tickers = df["Ticker"].unique().tolist()
    current_prices = {t: get_current_price(t) for t in tickers}

    cum_values = []
    total_units = {}
    for _, row in df.iterrows():
        total_units.setdefault(row["Ticker"], 0.0)
        total_units[row["Ticker"]] += row["Shares"]
        cv = sum(units * current_prices[t] for t, units in total_units.items())
        cum_values.append(cv)

    df["Cumulative Value"] = cum_values
    chart_df = df.set_index("Buy Date")[["Cumulative Cost","Cumulative Value"]]
    st.line_chart(chart_df)

    total_cost  = df["Cost"].sum()
    total_value = cum_values[-1]
    gain        = total_value - total_cost
    gain_pct    = (gain / total_cost * 100) if total_cost else 0
    c1, c2, c3 = st.columns(3)
    c1.metric("💰 Invested",   f"${total_cost:,.2f}")
    c2.metric("📈 Value Now",  f"${total_value:,.2f}")
    c3.metric("📊 Gain/Loss",  f"${gain:,.2f}", delta=f"{gain_pct:.2f}%")
else:
    st.info("No portfolio data to display cumulative investment.")
