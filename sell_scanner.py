import yfinance as yf
import pandas as pd
import os
import glob
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')

def calculate_wavetrend(df, ch_len=9, avg_len=12, sma_len=3):
    ap = (df['High'] + df['Low'] + df['Close']) / 3.0
    esa = ap.ewm(span=ch_len, adjust=False).mean()
    d = (ap - esa).abs().ewm(span=ch_len, adjust=False).mean()
    ci = (ap - esa) / (0.015 * d)
    wt1 = ci.ewm(span=avg_len, adjust=False).mean()
    wt2 = wt1.rolling(window=sma_len).mean()
    return wt1, wt2

def calculate_stoch_rsi(series, period=14, smoothK=3):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    rsi = 100 - (100 / (1 + gain / loss))
    
    stoch = (rsi - rsi.rolling(period).min()) / (rsi.rolling(period).max() - rsi.rolling(period).min()) * 100
    return stoch.rolling(smoothK).mean()

if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    
    try:
        with open("portfolio.txt", "r") as f:
            tickers = [line.strip().upper() for line in f if line.strip()]
    except FileNotFoundError:
        print("portfolio.txt not found.")
        exit()

    results = []
    print(f"🔍 Scanning {len(tickers)} portfolio stocks for exit signals...")
    
    for ticker in tickers:
        try:
            df_daily = yf.download(ticker, period="1y", interval="1d", progress=False)
            df_weekly = yf.download(ticker, period="2y", interval="1wk", progress=False)
            
            if df_daily.empty or df_weekly.empty: continue
                
            d_wt1, d_wt2 = calculate_wavetrend(df_daily)
            d_stoch_rsi = calculate_stoch_rsi(df_daily['Close'])
            
            w_wt1, w_wt2 = calculate_wavetrend(df_weekly)
            
            # Daily triggers
            daily_red_dot = (d_wt1.iloc[-1] < d_wt2.iloc[-1]) and (d_wt1.iloc[-2] >= d_wt2.iloc[-2])
            strat1 = daily_red_dot and (d_wt1.iloc[-2] >= 53) # Red Zone cross
            
            # Weekly / Stoch Triggers
            weekly_red_dot = (w_wt1.iloc[-1] < w_wt2.iloc[-1]) and (w_wt1.iloc[-2] >= w_wt2.iloc[-2])
            stoch_overbought = d_stoch_rsi.iloc[-1] >= 80 # White dotted line
            strat2 = stoch_overbought or weekly_red_dot
            
            status = []
            if strat1: status.append("🔴 S1: Daily Red Dot (Red Zone)")
            if stoch_overbought: status.append("📈 S2: StochRSI Overbought (>= 80)")
            if weekly_red_dot: status.append("🔴 S2: Weekly Red Dot")
                    
            if status:
                results.append({
                    "Ticker": ticker,
                    "Close Price": round(float(df_daily['Close'].iloc[-1]), 2),
                    "Sell Alerts": " | ".join(status),
                    "Daily WT1": round(float(d_wt1.iloc[-1]), 1),
                    "StochRSI": round(float(d_stoch_rsi.iloc[-1]), 1)
                })
        except Exception:
            pass
            
    # Auto-cleanup old sell signals
    for f in glob.glob("sell_signals_*.csv"):
        if today not in f: os.remove(f)
            
    df_results = pd.DataFrame(results)
    filename = f"sell_signals_{today}.csv"
    
    if not df_results.empty:
        df_results.to_csv(filename, index=False)
        print(f"🚨 Found {len(df_results)} exit alerts! Saved to {filename}")
    else:
        pd.DataFrame(columns=["Ticker", "Close Price", "Sell Alerts", "Daily WT1", "StochRSI"]).to_csv(filename, index=False)
        print("✅ No sell signals found today.")