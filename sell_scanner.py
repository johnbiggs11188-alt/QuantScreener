import yfinance as yf
import pandas as pd
import numpy as np
import os
import glob
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')

def calculate_wavetrend(df, ch_len=9, avg_len=12, sma_len=3):
    high = df['High'].squeeze()
    low = df['Low'].squeeze()
    close = df['Close'].squeeze()
    
    ap = (high + low + close) / 3.0
    esa = ap.ewm(span=ch_len, adjust=False).mean()
    d = (ap - esa).abs().ewm(span=ch_len, adjust=False).mean()
    ci = (ap - esa) / (0.015 * d.replace(0, np.nan))
    ci = ci.fillna(0.0)
    wt1 = ci.ewm(span=avg_len, adjust=False).mean()
    wt2 = wt1.rolling(window=sma_len).mean()
    
    # Crossunder: wt1 crosses below wt2
    r_dot_live = (wt1.iloc[-1] < wt2.iloc[-1]) and (wt1.iloc[-2] >= wt2.iloc[-2])
    r_dot_prev = (wt1.iloc[-2] < wt2.iloc[-2]) and (wt1.iloc[-3] >= wt2.iloc[-3])
    
    return wt1, wt2, r_dot_live, r_dot_prev

def calculate_stoch_rsi(series, period=14, smoothK=3):
    series = series.squeeze()
    delta = series.diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.fillna(50)
    
    lowest_rsi = rsi.rolling(period).min()
    highest_rsi = rsi.rolling(period).max()
    denom = highest_rsi - lowest_rsi
    
    stoch = ((rsi - lowest_rsi) / denom.replace(0, np.nan)) * 100
    stoch = stoch.fillna(0)
    k = stoch.rolling(smoothK).mean()
    return k

def check_fib_red_zone(df_daily, lookback=252):
    high = df_daily['High'].squeeze()
    low = df_daily['Low'].squeeze()
    close = df_daily['Close'].squeeze()
    
    f_high = high.rolling(window=lookback, min_periods=20).max().iloc[-1]
    f_low = low.rolling(window=lookback, min_periods=20).min().iloc[-1]
    fib_range = f_high - f_low
    
    fib_0786 = f_low + (fib_range * 0.786)
    current_close = close.iloc[-1]
    
    return current_close >= fib_0786

if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    portfolio = []
    
    try:
        with open("portfolio.txt", "r") as f:
            for line in f:
                if not line.strip(): 
                    continue
                parts = line.strip().split(',')
                ticker = parts[0].strip().upper()
                shares = float(parts[1].strip()) if len(parts) > 1 else 0.0
                cost = float(parts[2].strip()) if len(parts) > 2 else 0.0
                
                if ticker != "CASH":
                    portfolio.append({"ticker": ticker, "shares": shares, "cost": cost})
    except FileNotFoundError:
        print("portfolio.txt not found.")
        exit()

    sell_signals = []
    dashboard_data = []
    
    print("🔍 Scanning portfolio against Overkill LDD rules...")
    
    for pos in portfolio:
        ticker = pos["ticker"]
        shares = pos["shares"]
        cost_basis = pos["cost"]
        
        try:
            df_daily = yf.download(ticker, period="2y", interval="1d", auto_adjust=True, progress=False)
            if df_daily.empty: 
                continue
            if isinstance(df_daily.columns, pd.MultiIndex):
                df_daily.columns = df_daily.columns.get_level_values(0)
                
            current_price = float(df_daily['Close'].iloc[-1])
            prev_price = float(df_daily['Close'].iloc[-2])
            
            day_change_dol = current_price - prev_price
            day_change_pct = (day_change_dol / prev_price) * 100
            curr_balance = shares * current_price
            
            if cost_basis > 0:
                unrealized_dol = curr_balance - (shares * cost_basis)
                unrealized_pct = (unrealized_dol / (shares * cost_basis)) * 100
            else:
                unrealized_dol = 0.0
                unrealized_pct = 0.0
            
            dashboard_data.append({
                "Symbol": ticker,
                "Price": current_price,
                "$ Change": day_change_dol,
                "% Change": day_change_pct,
                "Quantity": shares,
                "$ Unrealized": unrealized_dol,
                "% Unrealized": unrealized_pct,
                "Current Balance": curr_balance
            })
            
            # Skip sell calculation for core index ETF
            if ticker == "VOO":
                continue
                
            df_weekly = yf.download(ticker, period="3y", interval="1wk", auto_adjust=True, progress=False)
            if df_weekly.empty: 
                continue
            if isinstance(df_weekly.columns, pd.MultiIndex):
                df_weekly.columns = df_weekly.columns.get_level_values(0)
                
            # Calculations matching PineScript
            d_wt1, d_wt2, d_rdot_live, d_rdot_prev = calculate_wavetrend(df_daily)
            in_red_zone = check_fib_red_zone(df_daily, lookback=252)
            
            w_wt1, w_wt2, w_rdot_live, w_rdot_prev = calculate_wavetrend(df_weekly)
            w_stoch = calculate_stoch_rsi(df_weekly['Close'])
            
            # --- PineScript Sell Rule Definitions ---
            # Sell 1 (1DR): Daily red dot AND in 0.786 Fib Red Zone
            sell_strat1 = (d_rdot_live or d_rdot_prev) and in_red_zone
            
            # Sell 2 (1WR): Weekly red dot (live or confirmed) OR Weekly StochRSI >= 99
            w_rdot = w_rdot_live or w_rdot_prev
            w_stoch_extreme = float(w_stoch.iloc[-1]) >= 99.0
            sell_strat2 = w_rdot or w_stoch_extreme
            
            alerts = []
            if sell_strat1:
                alerts.append("🔴 Sell 1: Daily Red Dot (In Red Zone)")
            if w_rdot:
                status_label = "Current Week" if w_rdot_live else "Confirmed Last Week"
                alerts.append(f"🔴 Sell 2: Weekly Red Dot ({status_label})")
            if w_stoch_extreme:
                alerts.append("📈 Sell 2: Weekly StochRSI >= 99")
                
            if alerts:
                sell_signals.append({
                    "Ticker": ticker,
                    "Close Price": round(current_price, 2),
                    "Sell Alerts": " | ".join(alerts),
                    "Weekly WT1": round(float(w_wt1.iloc[-1]), 1),
                    "Weekly StochRSI": round(float(w_stoch.iloc[-1]), 1)
                })
        except Exception as e:
            print(f"Error processing {ticker}: {e}")

    # Cleanup old CSV files
    for f in glob.glob("sell_signals_*.csv") + glob.glob("portfolio_dashboard_*.csv"):
        if today not in f:
            try: 
                os.remove(f)
            except: 
                pass
            
    # Save CSV outputs
    df_dash = pd.DataFrame(dashboard_data)
    if not df_dash.empty:
        df_dash.to_csv(f"portfolio_dashboard_{today}.csv", index=False)
        
    df_sell = pd.DataFrame(sell_signals)
    if not df_sell.empty:
        df_sell.to_csv(f"sell_signals_{today}.csv", index=False)
    else:
        pd.DataFrame(columns=["Ticker", "Close Price", "Sell Alerts", "Weekly WT1", "Weekly StochRSI"]).to_csv(f"sell_signals_{today}.csv", index=False)
        
    print(f"✅ Finished scan. Found {len(df_sell)} active sell alert(s).")