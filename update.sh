#!/bin/bash

echo "🚀 Starting the Daily Quant Scan..."
source venv/bin/activate
python scanner.py
python sell_scanner.py

echo "☁️ Pushing new data to GitHub..."
git add .
git commit -m "Daily signal update"
git push

echo "📊 Launching local dashboard..."
streamlit run app.py