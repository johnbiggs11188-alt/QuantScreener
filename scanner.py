import yfinance as yf
import pandas as pd
import requests
from io import StringIO
import logging
import warnings
import time
import os
import glob
from datetime import datetime

logging.getLogger('yfinance').setLevel(logging.CRITICAL)
warnings.filterwarnings('ignore')

def get_ticker_list():
    urls = [
        'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies',
        'https://en.wikipedia.org/wiki/List_of_S%26P_400_companies',
        'https://en.wikipedia.org/wiki/List_of_S%26P_600_companies'
    ]
    headers = {'User-Agent': 'Mozilla/5.0'}
    all_raw_tickers = []
    
    for url in urls:
        response = requests.get(url, headers=headers)
        wiki_table = pd.read_html(StringIO(response.text))[0]
        tickers = [t.replace('.', '-') for t in wiki_table['Symbol'].tolist()]
        all_raw_tickers.extend(tickers)
        
    adrs = [
        "TSM", "NVO", "ASML", "TM", "NVS", "AZN", "SAP", "SHEL", "BABA", "TTE", 
        "UL", "HSBC", "HDB", "BHP", "BTI", "SONY", "RY", "TD", "MUFG", "BP", 
        "INFY", "RIO", "ENB", "SNY", "CNI", "CP", "UBS", "TRI", "IBN", "RELX",
        "DEO", "MFC", "BNS", "SU", "BMO", "JD", "ITUB", "ABEV", "PBR", "VALE", 
        "NU", "MELI", "ARM", "SPOT", "SHOP", "RACE", "STLA", "FMS", "PHG", "NOK", 
        "ERIC", "LOGI", "NTES", "BIDU", "MDT", "CB", "AON", "TRP", "BCE", "CM", 
        "TEF", "SAN", "BBVA", "ING", "RDY", "HMC", "CAJ", "TAK", "MFG", "IX", 
        "NMR", "SMFG", "ORAN", "VOD", "WPP", "PUK", "BAM", "BN", "BCS", "LYG", 
        "NWG", "RYAAY", "LU", "ZTO", "TME", "BEKE", "EDU", "HTHT", "GDS", "WFG",
        "QSR", "ERJ", "GGB", "SID", "CIG", "BBD", "LTM"
    ]
    all_raw_tickers.extend(adrs)
    return sorted(list(set(all_raw_tickers)))

def load_global_market_data(interval, today_str):
    cache_filename = f"raw_data_{interval}_{today_str}.pkl"
    raw_tickers = get_ticker_list()

    # Instant reload if scanned today
    if os.path.exists(cache_filename):
        print(f"⚡ Loading cached {interval} market data from {cache_filename}...")
        return pd.read_pickle(cache_filename), raw_tickers

    print(f"Downloading fresh {interval} data for {len(raw_tickers)} tickers...")
    chunk_size = 250
    all_data = []
    
    for i in range(0, len(raw_tickers), chunk_size):
        chunk = raw_tickers[i:i+chunk_size]
        if len(chunk) == 1: 
            chunk.append('SPY') 
        
        print(f" -> Fetching chunk {i+1} to {i+len(chunk)}...")
        data_chunk = yf.download(
            chunk, 
            period="max", 
            interval=interval, 
            group_by='ticker', 
            threads=False, 
            progress=False, 
            auto_adjust=True
        )
        all_data.append(data_chunk)
        time.sleep(2) 
        
    full_df = pd.concat(all_data, axis=1)
    
    # Save cache locally
    full_df.to_pickle(cache_filename)
    print(f"💾 Raw {interval} market data cached to {cache_filename}")
    return full_df, raw_tickers

def calculate_wavetrend(df, ch_len=9, avg_len=12, sma_len=3):
    ap = (df['High'] + df['Low'] + df['Close']) / 3.0
    esa = ap.ewm(span=ch_len, adjust=False).mean()
    d = (ap - esa).abs().ewm(span=ch_len, adjust=False).mean()
    ci = (ap - esa) / (0.015 * d)
    wt1 = ci.ewm(span=avg_len, adjust=False).mean()
    wt2 = wt1.rolling(window=sma_len).mean()
    return wt1, wt2

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def check_bullish_divergence(df, wt1, lookback=30, offset=0):
    current_low = df['Low'].iloc[-1 - offset]
    current_wt = wt1.iloc[-1 - offset]
    
    past_window_low = df['Low'].iloc[-lookback - offset : -3 - offset]
    past_window_wt = wt1.iloc[-lookback - offset : -3 - offset]
    
    if past_window_low.empty:
        return False
        
    prev_lowest_price = past_window_low.min()
    prev_lowest_wt = past_window_wt.min()
    
    return bool((current_low < prev_lowest_price) and (current_wt > prev_lowest_wt))

def safe_get(info_dict, key, default=0.0):
    val = info_dict.get(key)
    return float(val) if val is not None else default

def generate_quant_grades(survivors_dict):
    raw_data = []
    for ticker, meta in survivors_dict.items():
        try:
            info = yf.Ticker(ticker).info
            debt_eq = safe_get(info, 'debtToEquity', 0) 
            fcf = safe_get(info, 'freeCashflow', 0)
            
            if debt_eq > 200 or fcf < 0:
                continue 
                
            market_cap = safe_get(info, 'marketCap', 1)
            raw_data.append({
                'Ticker': ticker,
                'Floor Tier': meta['Tier'],
                'Status': meta['Status'],
                'Close Price': meta['Close'],
                'FCF_Yield': fcf / market_cap if market_cap > 1 else 0,
                'ROA': safe_get(info, 'returnOnAssets', 0),
                'EV_EBITDA': safe_get(info, 'enterpriseToEbitda', 100)
            })
        except Exception:
            pass
        time.sleep(1.5)
        
    df = pd.DataFrame(raw_data)
    if df.empty: 
        return df
    
    df['FCF_Score'] = df['FCF_Yield'].rank(pct=True) * 100
    df['ROA_Score'] = df['ROA'].rank(pct=True) * 100
    df['EV_Score'] = df['EV_EBITDA'].rank(pct=True, ascending=False) * 100
    
    df['Final_Grade'] = (df['FCF_Score'] * 0.40) + (df['ROA_Score'] * 0.30) + (df['EV_Score'] * 0.30)
    df['Final_Grade'] = df['Final_Grade'].round(1)
    
    return df[['Ticker', 'Final_Grade', 'Floor Tier', 'Status', 'Close Price', 'FCF_Yield', 'ROA', 'EV_EBITDA']].sort_values(
        by=['Final_Grade'], ascending=False
    ).reset_index(drop=True)

if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    
    # --- AUTO-CLEANUP OLD YAHOO CACHE FILES ---
    for f in glob.glob("raw_data_*.pkl"):
        if today not in f:
            os.remove(f)
            print(f"🗑️ Deleted old Yahoo data file: {f}")
            
    timeframes = [("Monthly", "1mo"), ("Weekly", "1wk"), ("Daily", "1d")]
    
    for timeframe, interval in timeframes:
        print(f"\n========================================")
        print(f"🚀 STARTING {timeframe.upper()} PIPELINE")
        print(f"========================================")
        
        data, raw_tickers = load_global_market_data(interval, today)
        survivors_metadata = {}
        
        for t in raw_tickers:
            try:
                if t not in data.columns.levels[0]: 
                    continue
                df = data[t].dropna(how='all')
                if len(df) < 36: 
                    continue
                
                df = df.dropna()
                wt1, wt2 = calculate_wavetrend(df)
                rsi = calculate_rsi(df['Close'])
                
                if len(wt1) < 3: 
                    continue

                wt1_now, wt2_now = wt1.iloc[-1], wt2.iloc[-1]
                wt1_1ago, wt2_1ago = wt1.iloc[-2], wt2.iloc[-2]
                wt1_2ago, wt2_2ago = wt1.iloc[-3], wt2.iloc[-3]
                
                rsi_now = rsi.iloc[-1]
                rsi_1ago = rsi.iloc[-2]

                live_cross = (wt1_now > wt2_now) and (wt1_1ago <= wt2_1ago) and (wt1_now < 0)
                confirmed_cross = (wt1_1ago > wt2_1ago) and (wt1_2ago <= wt2_2ago) and (wt1_1ago < 0)

                if timeframe == "Daily":
                    # 1. Gold Dot rules
                    live_gold = live_cross and (wt1_now <= -80) and (rsi_now < 20) and check_bullish_divergence(df, wt1, offset=0)
                    posted_gold = confirmed_cross and (wt1_1ago <= -80) and (rsi_1ago < 20) and check_bullish_divergence(df, wt1, offset=1)
                    
                    # 2. Strong Green Dot rules: cross up below -60
                    live_strong = live_cross and (wt1_now <= -60)
                    posted_strong = confirmed_cross and (wt1_1ago <= -60)
                    
                    if live_gold or posted_gold:
                        status = "Live Gold Dot (Today)" if live_gold else "Posted Gold Dot (Yesterday)"
                        close_price = df['Close'].iloc[-1] if live_gold else df['Close'].iloc[-2]
                        survivors_metadata[t] = {'Tier': "🟡 Gold Dot", 'Status': status, 'Close': round(close_price, 2)}
                    elif live_strong or posted_strong:
                        status = "Live Strong Dot (Today)" if live_strong else "Posted Strong Dot (Yesterday)"
                        close_price = df['Close'].iloc[-1] if live_strong else df['Close'].iloc[-2]
                        survivors_metadata[t] = {'Tier': "🟢 Strong Green (< -60)", 'Status': status, 'Close': round(close_price, 2)}
                else:
                    if live_cross or confirmed_cross:
                        status = "Live (Unfinished)" if live_cross else "Confirmed (Previous)"
                        trigger_wt1 = wt1_now if live_cross else wt1_1ago
                        close_price = df['Close'].iloc[-1] if live_cross else df['Close'].iloc[-2]

                        if trigger_wt1 <= -53:
                            tier = "🟢🟢 Deep Floor"
                        elif trigger_wt1 <= -40:
                            tier = "🟢 Oversold Floor"
                        else:
                            tier = "⚪ Standard (< 0)"
                            
                        if timeframe == "Weekly" and tier == "⚪ Standard (< 0)":
                            continue
                            
                        survivors_metadata[t] = {'Tier': tier, 'Status': status, 'Close': round(close_price, 2)}
            except Exception:
                continue

        print(f"\nLayer 1 Complete! Found {len(survivors_metadata)} technical survivors for {timeframe}.")
        
        if survivors_metadata:
            print(f"Starting Layer 2: Fundamental Screen for {timeframe}...")
            final_df = generate_quant_grades(survivors_metadata)
            
            if not final_df.empty:
                filename = f"screener_results_{timeframe.lower()}_{today}.csv"
                final_df.to_csv(filename, index=False)
                print(f"{timeframe} Pipeline complete! Saved to {filename}")
            else:
                print(f"No stocks passed fundamental checks for {timeframe}.")
        else:
            print(f"No technical survivors found for {timeframe}.")