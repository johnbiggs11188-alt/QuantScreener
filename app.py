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

def load_sell_signals():
    list_of_files = glob.glob('sell_signals_*.csv')
    if not list_of_files:
        return None, None
    latest_file = sorted(list_of_files)[-1]
    return pd.read_csv(latest_file), latest_file

monthly_data, monthly_file = load_latest_results("monthly")
weekly_data, weekly_file = load_latest_results("weekly")
daily_data, daily_file = load_latest_results("daily")
sell_data, sell_file = load_sell_signals()

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
    st.markdown("**💰 Capital Allocation Calculator**")
    
    # Top Row: Balance and Inputs
    col_bal, col_add, col_tot = st.columns(3)
    current_balance = col_bal.number_input("Current Balance ($)", min_value=0.0, value=10000.0, step=100.0)
    new_deposit = col_add.number_input("New Deposit to Add ($)", min_value=0.0, value=300.0, step=50.0)
    
    total_capital = current_balance + new_deposit
    col_tot.metric("Total Locked-In Value (Z)", f"${total_capital:,.2f}")
    
    st.write("---")
    
    # Middle Row: The Allocation Breakdown
    st.markdown("**New Deposit Routing (10% Cash | 60% VOO | 30% Stocks)**")
    
    alloc_cash = new_deposit * 0.10
    alloc_voo = new_deposit * 0.60
    alloc_stocks = new_deposit * 0.30
    
    # 2.5% max position size based on the TOTAL new portfolio value
    max_per_stock = total_capital * 0.025 
    
    a1, a2, a3 = st.columns(3)
    a1.metric("💵 To Cash (10%)", f"${alloc_cash:,.2f}")
    a2.metric("📈 To VOO (60%)", f"${alloc_voo:,.2f}")
    a3.metric("🎯 To Stocks (30%)", f"${alloc_stocks:,.2f}")
    
    st.info(f"💡 **Max Position Rule:** With a total portfolio value of ${total_capital:,.2f}, your absolute maximum buy for any single stock (2.5%) is **${max_per_stock:,.2f}**.")
    
    st.write("---")
    
    # Bottom Row: Existing Sell Signals
    st.markdown("**🚨 Active Sell Signals**")
    if sell_data is None:
        st.info("No portfolio exit scan found. Run `python sell_scanner.py` to generate exit alerts.")
    else:
        st.caption(f"Loaded exit data from: `{sell_file}`")
        if not sell_data.empty:
            st.error(f"🚨 {len(sell_data)} Exit Alert(s) Triggered!")
            st.dataframe(
                sell_data,
                column_config={
                    "Ticker": st.column_config.TextColumn("Ticker", width="small"),
                    "Close Price": st.column_config.NumberColumn("Close Price", format="$%.2f"),
                    "Sell Alerts": st.column_config.TextColumn("Triggered Conditions"),
                    "Daily WT1": st.column_config.NumberColumn("Daily WT1", format="%.1f"),
                    "StochRSI": st.column_config.NumberColumn("StochRSI", format="%.1f"),
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.success("No sell signals triggered for your portfolio today.")