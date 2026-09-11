import os
import subprocess
import sys

def load_portfolio(filename="portfolio.txt"):
    portfolio = {}
    try:
        with open(filename, "r") as f:
            for line in f:
                if line.strip():
                    parts = line.strip().split(',')
                    sym = parts[0].strip()
                    qty = float(parts[1].strip())
                    cost = float(parts[2].strip())
                    portfolio[sym] = {'qty': qty, 'cost': cost}
    except FileNotFoundError:
        print(f"Error: {filename} not found.")
    return portfolio

def save_portfolio(portfolio, filename="portfolio.txt"):
    with open(filename, "w") as f:
        for sym, data in portfolio.items():
            f.write(f"{sym}, {data['qty']}, {data['cost']}\n")

def main():
    portfolio = load_portfolio()
    if not portfolio:
        return

    print("\n--- 🏦 Portfolio Sync ---")
    print("Press Enter on any prompt to skip and keep the current value.\n")
    
    # 1. Update Cash
    curr_cash = portfolio.get('CASH', {}).get('qty', 0.0)
    new_cash = input(f"Current CASH: ${curr_cash:,.2f}\nEnter NEW total Cash balance: ")
    if new_cash.strip():
        portfolio['CASH'] = {'qty': float(new_cash.replace('$', '').replace(',', '')), 'cost': 1.00}
        
    # 2. Update VOO
    curr_voo = portfolio.get('VOO', {}).get('qty', 0.0)
    new_voo = input(f"\nCurrent VOO shares: {curr_voo}\nEnter NEW total VOO shares: ")
    if new_voo.strip():
        cost = portfolio.get('VOO', {}).get('cost', 0.0)
        portfolio['VOO'] = {'qty': float(new_voo), 'cost': cost}
        
    # 3. Update Individual Stocks
    while True:
        ans = input("\nDid you buy or sell any other stocks today? (y/n): ").strip().lower()
        if ans != 'y':
            break
        
        ticker = input("Enter Ticker (e.g., AAPL): ").strip().upper()
        curr_qty = portfolio.get(ticker, {}).get('qty', 0.0)
        
        new_qty_str = input(f"Current {ticker} shares: {curr_qty}\nEnter NEW total shares (Type 0 if you sold everything): ").strip()
        if not new_qty_str:
            continue
            
        new_qty = float(new_qty_str)
        
        if new_qty == 0:
            if ticker in portfolio:
                del portfolio[ticker]
                print(f"🗑️ Removed {ticker} from portfolio.")
        else:
            new_cost = float(input(f"Enter NEW average cost per share for {ticker}: ").strip().replace('$', ''))
            portfolio[ticker] = {'qty': new_qty, 'cost': new_cost}
            print(f"✅ Updated {ticker}.")

    # 4. Save and Route Execution
    save_portfolio(portfolio)
    print("\n💾 portfolio.txt updated successfully!")
    
    # Check for terminal flag (e.g. `python sync.py --quick`)
    quick_mode = "--quick" in sys.argv or "--sell" in sys.argv
    
    if not quick_mode:
        print("\nChoose an action:")
        print(" [1] Quick Sell/Update (Only refresh portfolio & push to GitHub in ~5s)")
        print(" [2] Full Scan (Run complete Friday 1,600-ticker screener)")
        choice = input("Enter 1 or 2 [default: 1]: ").strip()
        if choice != "2":
            quick_mode = True

    if quick_mode:
        print("\n⚡ Running quick portfolio refresh...")
        subprocess.run(["python", "sell_scanner.py"], check=True)
        
        print("📤 Pushing portfolio changes to GitHub...")
        subprocess.run(["git", "add", "portfolio.txt"], check=True)
        subprocess.run(["git", "commit", "-m", "Quick portfolio balance update"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("✅ Dashboard updated in cloud successfully!")
    else:
        print("\n🚀 Launching fresh full scan...")
        subprocess.run(["./fresh_scan.sh"])

if __name__ == "__main__":
    main()