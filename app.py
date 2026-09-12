import streamlit as st
import pandas as pd
import glob
import os
import yfinance as yf
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Global Quant Screener", page_icon="📈", layout="wide")
st.title("📈 Global Quant Screener")

# --- DATA LOADERS FOR SCREENER RESULTS ---
def load_latest_results(timeframe):
    list_of_files = glob.glob(f'screener_results_{timeframe}_*.csv')
    if not list_of_files:
        return None, None
    latest_file = sorted(list_of_files)[-1] 
    return pd.read_csv(latest_file), latest_file

def load_sell_signals():
    sell_files = glob.glob('sell_signals_*.csv')
    sell_data = pd.read_csv(sorted(sell_files)[-1]) if sell_files else None
    return sell_data

# --- LIVE PORTFOLIO BUILDER (CACHED FOR 60 SECONDS) ---
@st.cache_data(ttl=60)
def get_live_portfolio_data():
    portfolio = []
    cash_balance = 0.0
    cost_dict = {}

    if not os.path.exists("portfolio.txt"):
        return None, 0.0, 0.0, None

    with open("portfolio.txt", "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            sym = parts[0].strip().upper()
            qty = float(parts[1].strip()) if len(parts) > 1 else 0.0
            cost = float(parts[2].strip()) if len(parts) > 2 else 0.0

            if sym == "CASH":
                cash_balance = qty
            else:
                portfolio.append({'ticker': sym, 'shares': qty, 'cost': cost})
                cost_dict[sym] = cost

    if not portfolio:
        return None, cash_balance, 0.0, cost_dict

    tickers = [p['ticker'] for p in portfolio]
    
    # Download latest 5 days to guarantee current and previous closes
    data = yf.download(tickers, period="5d", interval="1d", auto_adjust=True, progress=False)

    rows = []
    total_stock_balance = 0.0
    voo_balance = 0.0

    for p in portfolio:
        sym = p['ticker']
        shares = p['shares']
        cost = p['cost']

        try:
            if len(tickers) == 1:
                close_series = data['Close'].dropna()
            else:
                close_series = data['Close'][sym].dropna()

            curr_price = float(close_series.iloc[-1])
            prev_price = float(close_series.iloc[-2]) if len(close_series) >= 2 else curr_price
        except Exception:
            curr_price = cost
            prev_price = cost

        day_change_dol = curr_price - prev_price
        day_change_pct = (day_change_dol / prev_price) * 100 if prev_price > 0 else 0.0
        balance = shares * curr_price
        total_stock_balance += balance

        if sym == "VOO":
            voo_balance = balance

        unrealized_dol = (balance - (shares * cost)) if cost > 0 else 0.0

        rows.append({
            "Symbol": sym,
            "Price": curr_price,
            "$ Change": day_change_dol,
            "% Change": day_change_pct,
            "Quantity": shares,
            "Cost Basis": cost,
            "$ Unrealized": unrealized_dol,
            "Current Balance": balance
        })

    df = pd.DataFrame(rows)
    total_portfolio_equity = total_stock_balance + cash_balance

    if not df.empty and total_portfolio_equity > 0:
        df['% of Portfolio'] = (df['Current Balance'] / total_portfolio_equity) * 100
    else:
        df['% of Portfolio'] = 0.0

    return df, cash_balance, voo_balance, total_portfolio_equity

monthly_data, monthly_file = load_latest_results("monthly")
weekly_data, weekly_file = load_latest_results("weekly")
daily_data, daily_file = load_latest_results("daily")
sell_data = load_sell_signals()

# Sidebar Filters
st.sidebar.header("🎯 Quantitative Matrix Filters")

min_val = st.sidebar.slider("Min Valuation Rank (Cheapness)", min_value=0, max_value=100, value=50, step=5)
min_qual = st.sidebar.slider("Min Quality Rank (Profitability)", min_value=0, max_value=100, value=50, step=5)
max_leverage = st.sidebar.slider("Max Net Debt / EBITDA", min_value=0.0, max_value=3.5, value=3.5, step=0.5)

all_tiers = set()
all_statuses = set()
for df_temp in [monthly_data, weekly_data, daily_data]:
    if df_temp is not None and not df_temp.empty:
        if 'Floor Tier' in df_temp.columns:
            all_tiers.update(df_temp['Floor Tier'].dropna().unique())
        if 'Status' in df_temp.columns:
            all_statuses.update(df_temp['Status'].dropna().unique())

selected_tier = st.sidebar.multiselect("Technical Floor Tier:", options=list(all_tiers), default=list(all_tiers))
selected_status = st.sidebar.multiselect("Signal Status:", options=list(all_statuses), default=list(all_statuses))

tab1, tab2, tab3, tab4 = st.tabs(["Monthly", "Weekly", "Daily", "Portfolio"])

def render_dashboard(df, filename, tab_title):
    if df is None:
        st.info(f"No data available for {tab_title}.")
        return
        
    st.caption(f"Loaded data from: `{filename}`")
    filtered_df = df.copy()
    
    is_upgraded = 'Valuation_Rank' in filtered_df.columns and 'Quality_Rank' in filtered_df.columns
    
    if is_upgraded:
        filtered_df = filtered_df[
            (filtered_df['Valuation_Rank'] >= min_val) & 
            (filtered_df['Quality_Rank'] >= min_qual) &
            ((filtered_df['NetDebt_EBITDA'] <= max_leverage) | (filtered_df['Sector'].isin(['Financial Services', 'Financials']))) &
            (filtered_df['Floor Tier'].isin(selected_tier)) & 
            (filtered_df['Status'].isin(selected_status))
        ]
    else:
        if 'Final_Grade' in filtered_df.columns:
            filtered_df = filtered_df[
                (filtered_df['Final_Grade'] >= min_val) & 
                (filtered_df['Floor Tier'].isin(selected_tier)) & 
                (filtered_df['Status'].isin(selected_status))
            ]
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Technical Survivors", len(df))
    col2.metric("High Conviction (Filtered)", len(filtered_df))
    if not filtered_df.empty:
        col3.metric("Top Ranked Setup", filtered_df.iloc[0]['Ticker'])
        
    if not filtered_df.empty:
        if is_upgraded:
            st.dataframe(
                filtered_df,
                column_config={
                    "Ticker": st.column_config.TextColumn("Ticker", width="small"),
                    "Composite_Grade": st.column_config.ProgressColumn("Composite", format="%.1f", min_value=0, max_value=100),
                    "Valuation_Rank": st.column_config.NumberColumn("Val Rank", format="%.1f"),
                    "Quality_Rank": st.column_config.NumberColumn("Qual Rank", format="%.1f"),
                    "Floor Tier": st.column_config.TextColumn("Floor Tier"),
                    "Status": st.column_config.TextColumn("Status"),
                    "Close Price": st.column_config.NumberColumn("Price", format="$%.2f"),
                    "FCF_Yield": st.column_config.NumberColumn("FCF Yield", format="%.2f"),
                    "EV_EBITDA": st.column_config.NumberColumn("EV/EBITDA", format="%.2f"),
                    "NetDebt_EBITDA": st.column_config.NumberColumn("Net Debt/EBITDA", format="%.2f"),
                    "Op_Margin": st.column_config.NumberColumn("Op Margin", format="%.2f"),
                    "ROA": st.column_config.NumberColumn("ROA", format="%.2f"),
                    "Sector": st.column_config.TextColumn("Sector")
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.dataframe(
                filtered_df,
                column_config={
                    "Ticker": st.column_config.TextColumn("Ticker", width="small"),
                    "Final_Grade": st.column_config.ProgressColumn("Quant Grade", format="%.1f", min_value=0, max_value=100),
                    "Floor Tier": st.column_config.TextColumn("Floor Tier"),
                    "Status": st.column_config.TextColumn("Status"),
                    "Close Price": st.column_config.NumberColumn("Close Price", format="$%.2f"),
                    "FCF_Yield": st.column_config.NumberColumn("FCF Yield", format="%.2f"),
                    "ROA": st.column_config.NumberColumn("ROA", format="%.2f"),
                    "EV_EBITDA": st.column_config.NumberColumn("EV/EBITDA", format="%.2f")
                },
                hide_index=True,
                use_container_width=True
            )
    else:
        st.info("No stocks meet the current filter criteria.")

with tab1:
    render_dashboard(monthly_data, monthly_file, "Monthly")
    
with tab2:
    render_dashboard(weekly_data, weekly_file, "Weekly")

with tab3:
    render_dashboard(daily_data, daily_file, "Daily")

with tab4:
    st.markdown("### 📊 Live Portfolio Dashboard")
    
    col_refresh, _ = st.columns([1, 5])
    if col_refresh.button("🔄 Refresh Live Quotes"):
        st.cache_data.clear()
        st.rerun()

    dash_data, cash_balance, voo_balance, current_balance = get_live_portfolio_data()

    if dash_data is not None and not dash_data.empty:
        display_df = dash_data[["Symbol", "Current Balance", "% of Portfolio", "Quantity", "Cost Basis", "Price", "$ Change", "% Change", "$ Unrealized"]].copy()
        display_df.columns = ["SYMBOL", "BALANCE", "PORTFOLIO %", "QUANTITY", "COST BASIS", "CURRENT PRICE", "DAY $ CHANGE", "DAY % CHANGE", "GAIN/LOSS"]
        
        def format_dol(val):
            if pd.isna(val): return ""
            if val > 0: return f"▲ ${val:,.2f}"
            if val < 0: return f"▼ -${abs(val):,.2f}"
            return "$0.00"

        def format_pct(val):
            if pd.isna(val): return ""
            if val > 0: return f"▲ {val:.2f}%"
            if val < 0: return f"▼ -{abs(val):.2f}%"
            return "0.00%"

        def color_pnl(val):
            if pd.isna(val): return ""
            if val > 0: return 'color: #00C853;' 
            if val < 0: return 'color: #FF1744;' 
            return ''

        styled_dash = display_df.style.format({
            "BALANCE": "${:,.2f}",
            "PORTFOLIO %": "{:.2f}%",
            "QUANTITY": "{:.3f}",
            "COST BASIS": "${:,.2f}",
            "CURRENT PRICE": "${:,.2f}",
            "DAY $ CHANGE": format_dol,
            "DAY % CHANGE": format_pct,
            "GAIN/LOSS": format_dol
        })
        
        if hasattr(styled_dash, 'map'):
            styled_dash = styled_dash.map(color_pnl, subset=["DAY $ CHANGE", "DAY % CHANGE", "GAIN/LOSS"])
        else:
            styled_dash = styled_dash.applymap(color_pnl, subset=["DAY $ CHANGE", "DAY % CHANGE", "GAIN/LOSS"])

        st.dataframe(styled_dash, hide_index=True, use_container_width=True)
    else:
        st.info("No holdings found in portfolio.txt.")
        
    st.write("---")
    st.markdown("### 💰 Waterfall Capital Allocation")
    
    st.metric("Total Equity (Live Market Pricing)", f"${current_balance:,.2f}")
    
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    try:
        sheet_data = conn.read(
            spreadsheet="https://docs.google.com/spreadsheets/d/19_l6dc1QIBOfVJIUtakJinhZCsUt5rGNimM4-XRUuAU/edit?usp=sharing", 
            usecols=[2]
        )
        voo_deposits = sheet_data.iloc[:, 0].dropna()
        voo_deposits = voo_deposits[voo_deposits != ""]
        
        if not voo_deposits.empty:
            raw_value = str(voo_deposits.iloc[-1])
            clean_value = raw_value.replace('$', '').replace(',', '').strip()
            new_deposit = float(clean_value)
        else:
            new_deposit = 0.0
            
    except Exception as e:
        st.error(f"Google Sheets Error: {e}")
        new_deposit = 0.0

    st.write("---")
    apply_deposit = st.toggle(f"Apply new Google Sheets deposit (**${new_deposit:,.2f}**) to run waterfall math", value=False)
    
    active_deposit = new_deposit if apply_deposit else 0.0
    total_capital = current_balance + active_deposit
    effective_cash = cash_balance + active_deposit
    
    # Target allocations: 65% VOO, 10% Cash, 25% Stocks
    target_voo = total_capital * 0.65
    target_cash = total_capital * 0.10
    
    voo_deficit = max(0.0, target_voo - voo_balance)
    cash_deficit = max(0.0, target_cash - effective_cash)
    
    voo_status = "✅ Good" if voo_balance >= target_voo else f"⚠️ Short ${voo_deficit:,.2f}"
    cash_status = "✅ Good" if effective_cash >= target_cash else f"⚠️ Short ${cash_deficit:,.2f}"
    
    available_stocks = max(0.0, effective_cash - target_cash - voo_deficit)

    st.metric("Target Portfolio Value", f"${total_capital:,.2f}")
    
    st.markdown("**Current Portfolio Status**")
    a1, a2, a3 = st.columns(3)
    a1.metric("📈 VOO (Target: 65%)", voo_status)
    a2.metric("💵 Cash (Target: 10%)", cash_status)
    a3.metric("🎯 Available for Stocks (Target: 25%)", f"${available_stocks:,.2f}")
    
    max_per_stock = total_capital * 0.025 
    st.caption(f"💡 **Max Position Rule:** 2.5% maximum buy for any single stock is **${max_per_stock:,.2f}** based on Target Portfolio Value.")
    
    st.write("---")
    st.markdown("### 🚨 Active Sell Signals")
    if sell_data is None:
        st.info("No portfolio exit scan found.")
    else:
        if not sell_data.empty:
            st.error(f"🚨 {len(sell_data)} Exit Alert(s) Triggered!")
            st.dataframe(sell_data, hide_index=True, use_container_width=True)
        else:
            st.success("No sell signals triggered for your portfolio today.")