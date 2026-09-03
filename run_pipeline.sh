#!/bin/bash
cd /Users/johnbiggs/Desktop/QuantScreener
source venv/bin/activate
python scanner.py
git add screener_results_*.csv
git commit -m "Automated nightly scan update"
git push origin main