"""Download initial historical data for ETFs into updated_Results_for_scan"""
import yfinance as yf
import pandas as pd
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
results_dir = os.path.join(script_dir, 'updated_Results_for_scan')

etfs = [
    "SPY","QQQ","IWM","DIA","VTI","VOO",
    "XLF","XLE","XLK","XLV","XLP","XLI","XLB","XLU","XLRE","XLC","XLY",
    "TAN","ICLN","QCLN","ARKK","ARKG","ARKF","ARKW","ARKQ",
    "SOXX","SMH","HACK","CIBR","BOTZ","ROBO","CLOU","WCLD","DRIV","LIT","REMX","URA",
    "JETS","BLOK","BITO","IBIT",
    "GLD","SLV","USO","UNG","GDX","GDXJ","XME","XOP","AMLP","KRE","XHB","ITB",
    "TLT","HYG","LQD","AGG","BND",
    "EEM","EFA","VWO","VXUS","VEA","VGK","IEMG","KWEB","FXI","MCHI","INDA","EWJ","EWZ","EWY","ASHR",
    "VNQ","VNQI","SOXL","TQQQ","SQQQ","SPXL","TNA","TMF","UVXY",
]

print(f"Downloading {len(etfs)} ETFs...")
print(f"Saving to: {results_dir}\n")

success = 0
failed = 0

for etf in etfs:
    file_path = os.path.join(results_dir, f"{etf}.csv")

    if os.path.exists(file_path):
        print(f"  {etf}: Already exists, skipping")
        success += 1
        continue

    try:
        data = yf.download(etf, period="2y", progress=False, auto_adjust=True)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        if data.empty:
            print(f"  {etf}: No data returned")
            failed += 1
            continue
        data.to_csv(file_path)
        print(f"  {etf}: Downloaded {len(data)} rows")
        success += 1
    except Exception as e:
        print(f"  {etf}: ERROR - {e}")
        failed += 1

print(f"\nDone! Success: {success}, Failed: {failed}")
