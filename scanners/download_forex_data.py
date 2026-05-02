"""Download initial historical data for forex pairs into updated_Results_for_scan"""
import yfinance as yf
import pandas as pd
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
results_dir = os.path.join(script_dir, 'updated_Results_for_scan')

forex_pairs = [
    # Majors
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X",
    "AUDUSD=X", "USDCAD=X", "NZDUSD=X",
    # Crosses
    "EURGBP=X", "EURJPY=X", "GBPJPY=X", "AUDJPY=X",
    "EURAUD=X", "EURCHF=X", "GBPCHF=X", "CADJPY=X",
    "AUDNZD=X", "GBPAUD=X", "NZDJPY=X",
    # Exotics
    "USDMXN=X", "USDZAR=X", "USDTRY=X", "USDSEK=X",
    "USDNOK=X", "USDDKK=X", "USDSGD=X", "USDHKD=X",
    "USDCNH=X", "USDTHB=X", "USDPLN=X", "USDHUF=X",
    "USDCZK=X", "EURPLN=X", "EURTRY=X", "GBPNZD=X",
    "EURNZD=X",
]

print(f"Downloading {len(forex_pairs)} forex pairs...")
print(f"Saving to: {results_dir}\n")

success = 0
failed = 0

for pair in forex_pairs:
    file_path = os.path.join(results_dir, f"{pair}.csv")

    if os.path.exists(file_path):
        print(f"  {pair}: Already exists, skipping")
        success += 1
        continue

    try:
        data = yf.download(pair, period="2y", progress=False, auto_adjust=True)

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        if data.empty:
            print(f"  {pair}: No data returned")
            failed += 1
            continue

        data.to_csv(file_path)
        print(f"  {pair}: Downloaded {len(data)} rows")
        success += 1

    except Exception as e:
        print(f"  {pair}: ERROR - {e}")
        failed += 1

print(f"\nDone! Success: {success}, Failed: {failed}")
