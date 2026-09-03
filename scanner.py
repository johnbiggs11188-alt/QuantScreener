import yfinance as yf
import pandas as pd
import requests
from io import StringIO
import logging
import warnings
import time
from datetime import datetime

logging.getLogger('yfinance').setLevel(logging.CRITICAL)
warnings.filterwarnings('ignore')

def load_global_market_data(interval):
    """Fetches S&P 1500 + Top 100 International ADRs. Accepts '1mo' or '1wk'."""
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
    all_raw_tickers = list(set(all_raw_tickers))
    
    print(f"Downloading {interval} data for {len(all_raw_tickers)} tickers...")
    
    chunk_size = 250
    all_data = []
    
    for i in range(0, len(all_raw_tickers), chunk_size):
        chunk = all_raw_tickers[i:i+chunk_size]
        if len(chunk) == 1: chunk.append('SPY') 
        
        print(f" -> Fetching chunk {i+1} to {i+len(chunk)}...")
        data_chunk = yf.download(chunk, period="max", interval=interval, group_by='ticker', threads=False, progress=False, auto_adjust=True)
        all_data.append(data_chunk)
        time.sleep(2) 
        
    return pd.concat(all_data, axis=1), all_raw_tickers

def calculate_wavetrend(df, ch_len=9, avg_len=12, sma_len=3):
    ap = (df['High'] + df['Low'] + df['Close']) / 3.0
    esa = ap.ewm(span=ch_len, adjust=False).mean()
    d = (ap - esa).abs().ewm(span=ch_len, adjust=False).mean()
    ci = (ap - esa) / (0.015 * d)
    wt1 = ci.ewm(span=avg_len, adjust=False).mean()
    wt2 = wt1.rolling(window=sma_len).mean()
    return wt1, wt2

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
    if df.empty: return df
    
    df['FCF_Score'] = df['FCF_Yield'].rank(pct=True) * 100
    df['ROA_Score'] = df['ROA'].rank(pct=True) * 100
    df['EV_Score'] = df['EV_EBITDA'].rank(pct=True, ascending=False) * 100
    
    df['Final_Grade'] = (df['FCF_Score'] * 0.40) + (df['ROA_Score'] * 0.30) + (df['EV_Score'] * 0.30)
    df['Final_Grade'] = df['Final_Grade'].round(1)
    return df[['Ticker', 'Final_Grade', 'Floor Tier', 'Status', 'Close Price', 'FCF_Yield', 'ROA', 'EV_EBITDA']].sort_values(by=['Final_Grade'], ascending=False).reset_index(drop=True)

if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    
    # We loop twice: First Monthly, then Weekly.
    for timeframe, interval in [("Monthly", "1mo"), ("Weekly", "1wk")]:
        print(f"\n========================================")
        print(f"🚀 STARTING {timeframe.upper()} PIPELINE")
        print(f"========================================")
        
        data, raw_tickers = load_global_market_data(interval)
        survivors_metadata = {}
        
        for t in raw_tickers:
            try:
                if t not in data.columns.levels[0]: continue
                df = data[t].dropna(how='all')
                if len(df) < 36: continue
                
                df = df.dropna()
                wt1, wt2 = calculate_wavetrend(df)
                if len(wt1) < 3: continue

                wt1_now, wt2_now = wt1.iloc[-1], wt2.iloc[-1]
                wt1_1ago, wt2_1ago = wt1.iloc[-2], wt2.iloc[-2]
                wt1_2ago, wt2_2ago = wt1.iloc[-3], wt2.iloc[-3]

                live_cross = (wt1_now > wt2_now) and (wt1_1ago <= wt2_1ago) and (wt1_now < 0)
                confirmed_cross = (wt1_1ago > wt2_1ago) and (wt1_2ago <= wt2_2ago) and (wt1_1ago < 0)

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
                        
                    # EXCLUSIVE RULE: If Weekly, throw away "Standard" signals
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
                # Saves two distinct files: screener_results_monthly_DATE.csv and screener_results_weekly_DATE.csv
                filename = f"screener_results_{timeframe.lower()}_{today}.csv"
                final_df.to_csv(filename, index=False)
                print(f"{timeframe} Pipeline complete! Saved to {filename}")
            else:
                print(f"No stocks passed fundamental checks for {timeframe}.")
        else:
            print(f"No technical survivors found for {timeframe}.")