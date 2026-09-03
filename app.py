import streamlit as st
import pandas as pd
import glob
import os

st.set_page_config(page_title="Global Quant Screener", page_icon="📈", layout="wide")
st.title("📈 Global Quant Screener")

@st.cache_data
def load_latest_results(timeframe):
    list_of_files = glob.glob(f'screener_results_{timeframe}_*.csv')
    if not list_of_files:
        return None, None
    latest_file = max(list_of_files, key=os.path.getctime)
    return pd.read_csv(latest_file), latest_file

monthly_data, monthly_file = load_latest_results("monthly")
weekly_data, weekly_file = load_latest_results("weekly")
daily_data, daily_file = load_latest_results("daily")

if monthly_data is None and weekly_data is None and daily_data is None:
    st.warning("No scans found. Run `python scanner.py` in your terminal.")
    st.stop()

st.sidebar.header("Filter Setup")
min_grade = st.sidebar.slider("Minimum Quant Grade", min_value=0, max_value=100, value=70, step=5)

all_tiers = set()
all_statuses = set()
for df in [monthly_data, weekly_data, daily_data]:
    if df is not None:
        all_tiers.update(df['Floor Tier'].unique())
        all_statuses.update(df['Status'].unique())

selected_tier = st.sidebar.multiselect("Technical Floor Tier:", options=list(all_tiers), default=list(all_tiers))
selected_status = st.sidebar.multiselect("Signal Status:", options=list(all_statuses), default=list(all_statuses))

tab1, tab2, tab3 = st.tabs([
    "📅 Monthly Outlook", 
    "🗓️ Weekly (Deep & Oversold)", 
    "🟢 Daily Signals (Gold & Strong Green)"
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