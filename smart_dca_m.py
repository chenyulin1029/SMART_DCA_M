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
# 0. Read or initialize user_id via query_params
# -----------------------------------------------
qs = st.query_params

if "user_id" in qs and qs["user_id"]:
    user_id = qs["user_id"][0]
else:
    user_id = str(uuid.uuid4())
    # set it so this user gets their own file going forward
    st.experimental_set_query_params(user_id=user_id)

SESSION_FILE = f"portfolio_{user_id}.json"
GLOBAL_FILE  = "portfolio.json"


# -----------------------------------------------
# 1. Load tickers
# -----------------------------------------------
@st.cache_data
def load_valid_tickers():
    df = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
    return set(df["Symbol"].tolist() + ["QQQ", "NVDA"])
valid_tickers = load_valid_tickers()

# -----------------------------------------------
# 2. Utility functions
# -----------------------------------------------
def fetch_price(t, date):
    df = yf.download(t, start=date - datetime.timedelta(days=200),
                     end=date + datetime.timedelta(days=1),
                     progress=False, auto_adjust=False)
    col = "Adj Close" if "Adj Close" in df.columns else "Close"
    return float(df[col].loc[:pd.to_datetime(date)].iloc[-1])

def get_current_price(t):
    df = yf.download(t, period="2d", interval="1d", progress=False, auto_adjust=False)
    col = "Adj Close" if "Adj Close" in df.columns else "Close"
    return float(df[col].iloc[-1]) if not df.empty else 0.0

def validate_tickers(s):
    toks = [t.strip().upper() for t in s.split(",") if t.strip()]
    bad = [t for t in toks if t not in valid_tickers]
    if bad:
        raise ValueError(f"Invalid tickers: {bad}")
    return toks

def get_last_trade_and_buy_dates():
    today = datetime.date.today()
    offset = 1 if today.weekday() >= 5 else 0
    lt = today - datetime.timedelta(days=offset)
    bd = datetime.date(today.year, today.month, 15)
    while bd.weekday() >= 5: bd += datetime.timedelta(days=1)
    return today, lt, bd

# -----------------------------------------------
# 3. Smart DCA logic
# -----------------------------------------------
def run_dca(tks, counts, cd, bd, amt):
    prices = {t: fetch_price(t, cd) for t in tks}
    raw = {}
    for t in tks:
        p0 = prices[t]
        p1 = fetch_price(t, cd - datetime.timedelta(days=30))
        p3 = fetch_price(t, cd - datetime.timedelta(days=90))
        p6 = fetch_price(t, cd - datetime.timedelta(days=180))
        r1, r3, r6 = p0/p1-1, p0/p3-1, p0/p6-1
        raw[t] = 0.2*r1 + 0.3*r3 + 0.5*r6

    rot = counts.copy()
    sorted_raw = sorted(raw.items(), key=lambda x: x[1], reverse=True)
    for t,_ in sorted_raw:
        if rot.get(t,0) < 3:
            cand = t
            break
    else:
        cand = sorted_raw[0][0]
        for k in rot: rot[k]=0

    rot[cand] +=1
    for k in rot:
        if k!=cand: rot[k]=0

    price = prices[cand]
    shares = np.floor(amt/price*1000)/1000
    cost = shares*price

    return {"Buy Ticker":cand, "Price":price, "Shares":shares, "Cost":cost, "New Rotation":rot}

# -----------------------------------------------
# 4. Persistence helpers
# -----------------------------------------------
def load_portfolio():
    # on first use copy global file into the per‐user session file
    if os.path.exists(GLOBAL_FILE) and not os.path.exists(SESSION_FILE):
        try:
            with open(GLOBAL_FILE) as gf:
                jd = json.load(gf)
            with open(SESSION_FILE,"w") as sf:
                json.dump(jd, sf, indent=2)
        except:
            pass

    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE) as sf:
                jd = json.load(sf)
            df = pd.DataFrame(jd)
            for c in ["Buy Date","Ticker","Price","Shares","Cost"]:
                if c not in df: df[c]=np.nan
            return df[["Buy Date","Ticker","Price","Shares","Cost"]]
        except:
            pass

    return pd.DataFrame(columns=["Buy Date","Ticker","Price","Shares","Cost"])

def save_portfolio(df):
    d2 = df.copy()
    d2["Buy Date"]=d2["Buy Date"].astype(str)
    d2["Ticker"]=d2["Ticker"].astype(str)
    d2["Price"]=d2["Price"].astype(float)
    d2["Shares"]=d2["Shares"].astype(float)
    d2["Cost"]=d2["Cost"].astype(float)
    with open(SESSION_FILE,"w") as sf:
        json.dump(d2.to_dict(orient="records"), sf, indent=2)

# -----------------------------------------------
# 5. UI Layout
# -----------------------------------------------
st.title("📊 Smart DCA Investment Engine")

# Tickers input
ticker_str = st.text_input("Enter Tickers", value="QQQ,AAPL,NVDA")
st.markdown("#### … or pick from the universe")
ticker_list = st.multiselect("Select Tickers", sorted(valid_tickers), default=["QQQ","AAPL","NVDA"])
tickers_to_use = ticker_list if ticker_list else validate_tickers(ticker_str)

# Amount
preset = st.radio("Preset", ["$450 (Default)","$600 (Future)"])
custom = st.number_input("Or custom amount", 0.0,5000.0, step=10.0)
amount = 450 if (custom==0 and preset=="$450 (Default)") else (600 if custom==0 else custom)

today, lt, bd = get_last_trade_and_buy_dates()
cutoff_date = st.date_input("Cutoff Date", lt)
buy_date    = st.date_input("Buy Date",   bd)

# Rotation counts
st.markdown("### Rotation Counts")
if "rotation" not in st.session_state:
    st.session_state.rotation = {t:0 for t in tickers_to_use}
cols = st.columns(len(tickers_to_use))
init_counts = {}
for i,t in enumerate(tickers_to_use):
    init_counts[t] = cols[i].number_input(f"{t}", 0,3, st.session_state.rotation.get(t,0))

# Load portfolio
if "portfolio" not in st.session_state:
    st.session_state.portfolio = load_portfolio()

# Suggestion
if st.button("Suggest via Smart DCA"):
    try:
        res = run_dca(tickers_to_use, init_counts, cutoff_date, buy_date, amount)
        st.write(res)
        # … you can show your breakdown chart here …
        st.session_state.rotation = res["New Rotation"]
    except Exception as e:
        st.error(e)

# Manual entry
st.markdown("### ➕ Manually Add Purchase")
with st.form("m"):
    md = st.date_input("Buy Date", value=datetime.date.today())
    mt = st.selectbox("Ticker", sorted(valid_tickers))
    mp = st.number_input("Price", 0.01, step=0.01)
    ms = st.number_input("Shares",0.001,step=0.001)
    if st.form_submit_button("Add"):
        cost = mp*ms
        nr = {"Buy Date":str(md),"Ticker":mt,"Price":mp,"Shares":ms,"Cost":cost}
        st.session_state.portfolio = pd.concat(
            [st.session_state.portfolio, pd.DataFrame([nr])],
            ignore_index=True
        )
        save_portfolio(st.session_state.portfolio)
        st.success("Saved")

# Show/Edit/Delete
st.markdown("### 📜 Your Investment Portfolio")
if not st.session_state.portfolio.empty:
    key = f"ed_{len(st.session_state.portfolio)}"
    df2 = st.data_editor(st.session_state.portfolio, num_rows="dynamic", use_container_width=True, key=key)
    if not df2.equals(st.session_state.portfolio):
        st.session_state.portfolio = df2.reset_index(drop=True)
        save_portfolio(st.session_state.portfolio)
        st.success("Updated")
    with st.expander("🗑️ Delete a Row"):
        opts = [(i,f"{i}: {r.Ticker}@{r['Buy Date']}") for i,r in st.session_state.portfolio.iterrows()]
        ids,labels = zip(*opts)
        sel = st.selectbox("Delete row", options=ids, format_func=lambda i:labels[ids.index(i)])
        if st.button("Delete"):
            st.session_state.portfolio = st.session_state.portfolio.drop(sel).reset_index(drop=True)
            save_portfolio(st.session_state.portfolio)
            st.success("Deleted")
else:
    st.info("No purchases")


# 6. Smart DCA Suggestion
if st.button("Suggest via Smart DCA"):
    try:
        tickers = validate_tickers(",".join(tickers_to_use))
        res     = run_dca(tickers, init_counts,
                          cutoff_date, buy_date, amount)
        st.success("✅ Suggestion:")
        st.write(res)
    except Exception as e:
        st.error(f"❌ {e}")

# 7. Manual Entry
st.markdown("### ➕ Manually Add Purchase")
with st.form("manual_entry"):
    md = st.date_input("Buy Date", value=datetime.date.today())
    mt = st.selectbox("Ticker", sorted(valid_tickers))
    mp = st.number_input("Buy Price", min_value=0.01, step=0.01)
    ms = st.number_input("Shares",    min_value=0.001, step=0.001)
    if st.form_submit_button("Add Purchase"):
        cost = mp * ms
        nr   = {"Buy Date":str(md),
                "Ticker":  mt,
                "Price":   mp,
                "Shares":  ms,
                "Cost":    cost}
        st.session_state.portfolio = pd.concat(
            [st.session_state.portfolio, pd.DataFrame([nr])],
            ignore_index=True
        )
        save_portfolio(st.session_state.portfolio)
        st.success("Added & saved.")

# 8. Show/Edit/Delete Portfolio
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
        st.success("Portfolio updated and saved.")

    with st.expander("🗑️ Delete a Row"):
        opts = [
            (i, f"{i}: {r.Ticker} @ {r['Buy Date']} — {r.Shares} shares")
            for i, r in st.session_state.portfolio.iterrows()
        ]
        idxs, labels = zip(*opts)
        to_del = st.selectbox("Select row to delete", options=idxs,
                              format_func=lambda i: labels[idxs.index(i)])
        if st.button("Delete Selected Row", key="del"):
            st.session_state.portfolio = (
                st.session_state.portfolio
                  .drop(to_del)
                  .reset_index(drop=True)
            )
            save_portfolio(st.session_state.portfolio)
            st.success(f"Row {to_del} deleted.")
else:
    st.info("No portfolio data—add purchases above.")
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
        Total_Cost=("Cost",   "sum"),
        Current_Price=("Current Price", "mean"),
        Current_Value=("Current Value", "sum")
    )
    summary["Gain/Loss"] = summary["Current_Value"] - summary["Total_Cost"]
    st.dataframe(
      summary.style.format({
        "Total_Cost":    "${:.2f}",
        "Current_Price": "${:.2f}",
        "Current_Value": "${:.2f}",
        "Gain/Loss":     "${:.2f}"
      }),
      use_container_width=True
    )
else:
    st.info("No portfolio data to summarize.")

# 10. Allocation Pie
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
             color =alt.Color("Ticker:N", legend=alt.Legend(title="Ticker")),
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

# 11. Cumulative Investment Over Time
st.markdown("### 📈 Cumulative Investment & Current Value Over Time")
if not st.session_state.portfolio.empty:
    df = st.session_state.portfolio.copy()
    df["Buy Date"] = pd.to_datetime(df["Buy Date"])
    df = df.sort_values("Buy Date")
    df["Cumulative Cost"]  = df["Cost"].cumsum()
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

