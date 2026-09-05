#!/bin/bash

echo "🧹 Wiping cached data to force a fresh Yahoo Finance pull..."
rm raw_data_*.pkl 2>/dev/null

echo "🚀 Starting the Quant Scan..."
source venv/bin/activate
python scanner.py
python sell_scanner.py

echo "☁️ Pushing new data to GitHub..."
git add .
git commit -m "Fresh market data update"
git push

echo "📊 Launching local dashboard..."
streamlit run app.py