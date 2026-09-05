import streamlit as st
import pandas as pd
import glob
import os

st.set_page_config(page_title="Global Quant Screener", page_icon="📈", layout="wide")
st.title("📈 Global Quant Screener")

def load_latest_results(timeframe):
    list_of_files = glob.glob(f'screener_results_{timeframe}_*.csv')
    if not list_of_files:
        return None, None
    latest_file = sorted(list_of_files)[-1] 
    return pd.read_csv(latest_file), latest_file

def load_portfolio_files():
    dash_files = glob.glob('portfolio_dashboard_*.csv')
    dash_data = pd.read_csv(sorted(dash_files)[-1]) if dash_files else None
    
    sell_files = glob.glob('sell_signals_*.csv')
    sell_data = pd.read_csv(sorted(sell_files)[-1]) if sell_files else None
    
    return dash_data, sell_data

monthly_data, monthly_file = load_latest_results("monthly")
weekly_data, weekly_file = load_latest_results("weekly")
daily_data, daily_file = load_latest_results("daily")
dash_data, sell_data = load_portfolio_files()

if monthly_data is None and weekly_data is None and daily_data is None and sell_data is None:
    st.warning("No scans found. Run `python scanner.py` and `python sell_scanner.py` in your terminal.")
    st.stop()

st.sidebar.header("Filter Setup")
min_grade = st.sidebar.slider("Minimum Quant Grade", min_value=0, max_value=100, value=70, step=5)

all_tiers = set()
all_statuses = set()
for df in [monthly_data, weekly_data, daily_data]:
    if df is not None and not df.empty:
        if 'Floor Tier' in df.columns:
            all_tiers.update(df['Floor Tier'].dropna().unique())
        if 'Status' in df.columns:
            all_statuses.update(df['Status'].dropna().unique())

selected_tier = st.sidebar.multiselect("Technical Floor Tier:", options=list(all_tiers), default=list(all_tiers))
selected_status = st.sidebar.multiselect("Signal Status:", options=list(all_statuses), default=list(all_statuses))

tab1, tab2, tab3, tab4 = st.tabs([
    "📅 Monthly Outlook", 
    "🗓️ Weekly (Deep & Oversold)", 
    "🟢 Daily Signals (Gold & Strong Green)",
    "🚪 Portfolio Exits"
])

def render_dashboard(df, filename, tab_title):
    if df is None:
        st.info(f"No data available for {tab_title}.")
        return
        
    st.caption(f"Loaded data from: `{filename}`")
    
    filtered_df = df[
        (df['Final_Grade'] >= min_grade) & 
        (df['Floor Tier'].isin(selected_tier)) & 
        (df['Status'].isin(selected_status))
    ]
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Technical Survivors", len(df))
    col2.metric("High Conviction (Filtered)", len(filtered_df))
    if not filtered_df.empty:
        col3.metric("Top Ranked Setup", filtered_df.iloc[0]['Ticker'])
        
    if not filtered_df.empty:
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
    render_dashboard(daily_data, daily_file, "Daily Signals")

with tab4:
    st.markdown("### 📊 Live Portfolio Dashboard")
    
    cash_balance = 0.0
    try:
        with open("portfolio.txt", "r") as f:
            for line in f:
                if line.startswith("CASH"):
                    cash_balance = float(line.split(',')[1].strip())
    except:
        pass

    current_balance = cash_balance
    voo_balance = 0.0
    
    if dash_data is not None and not dash_data.empty:
        current_balance += dash_data['Current Balance'].sum()
        
        # Extract VOO for waterfall math
        voo_row = dash_data[dash_data['Symbol'] == 'VOO']
        if not voo_row.empty:
            voo_balance = voo_row.iloc[0]['Current Balance']
        
        # Calculate the % of Portfolio
        dash_data['% of Portfolio'] = (dash_data['Current Balance'] / current_balance) * 100
        
        # Reorder and rename columns
        display_df = dash_data[["Symbol", "Current Balance", "% of Portfolio", "Quantity", "Price", "$ Change", "% Change", "$ Unrealized"]].copy()
        display_df.columns = ["SYMBOL", "CURRENT BALANCE", "% OF PORTFOLIO", "QUANTITY", "CURRENT PRICE", "DAY $ CHANGE", "DAY % CHANGE", "LIFETIME GAIN/LOSS"]
        
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
            "CURRENT BALANCE": "${:,.2f}",
            "% OF PORTFOLIO": "{:.2f}%",
            "QUANTITY": "{:.3f}",
            "CURRENT PRICE": "${:,.2f}",
            "DAY $ CHANGE": format_dol,
            "DAY % CHANGE": format_pct,
            "LIFETIME GAIN/LOSS": format_dol
        })
        
        if hasattr(styled_dash, 'map'):
            styled_dash = styled_dash.map(color_pnl, subset=["DAY $ CHANGE", "DAY % CHANGE", "LIFETIME GAIN/LOSS"])
        else:
            styled_dash = styled_dash.applymap(color_pnl, subset=["DAY $ CHANGE", "DAY % CHANGE", "LIFETIME GAIN/LOSS"])

        st.dataframe(styled_dash, hide_index=True, use_container_width=True)
    else:
        st.info("No dashboard data found. Run `python sell_scanner.py`.")
        
    st.write("---")
    st.markdown("### 💰 Waterfall Capital Allocation")
    
    col_bal, col_add, col_tot = st.columns(3)
    col_bal.metric("Total Equity (Live)", f"${current_balance:,.2f}")
    new_deposit = col_add.number_input("New Deposit to Add ($)", min_value=0.0, value=300.0, step=50.0)
    
    total_capital = current_balance + new_deposit
    col_tot.metric("Target Portfolio Value", f"${total_capital:,.2f}")
    
    # --- WATERFALL MATH ---
    target_voo = total_capital * 0.60
    target_cash = total_capital * 0.10
    
    remaining_deposit = new_deposit
    
    # Priority 1: VOO (Up to 60%)
    voo_deficit = max(0.0, target_voo - voo_balance)
    alloc_voo = min(remaining_deposit, voo_deficit)
    remaining_deposit -= alloc_voo
    
    # Priority 2: Cash (Up to 10%)
    cash_deficit = max(0.0, target_cash - cash_balance)
    alloc_cash = min(remaining_deposit, cash_deficit)
    remaining_deposit -= alloc_cash
    
    # Priority 3: Stocks (Whatever is left)
    alloc_stocks = remaining_deposit
    
    st.markdown("**New Deposit Routing**")
    a1, a2, a3 = st.columns(3)
    a1.metric(f"📈 To VOO (Target: 60%)", f"${alloc_voo:,.2f}")
    a2.metric(f"💵 To Cash (Target: 10%)", f"${alloc_cash:,.2f}")
    a3.metric(f"🎯 To Stocks (Available)", f"${alloc_stocks:,.2f}")
    
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