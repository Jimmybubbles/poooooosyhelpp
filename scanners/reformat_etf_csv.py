import pandas as pd
import os

# Paths
script_dir = os.path.dirname(os.path.abspath(__file__))
input_file = os.path.join(script_dir, 'etfcsv.csv')
output_file = os.path.join(script_dir, 'CSV', 'etf_list.csv')

print("=" * 80)
print("REFORMATTING ETF CSV TO MATCH 5000.CSV FORMAT")
print("=" * 80)
print()

# Read the ETF CSV file (tab-separated based on the preview)
df = pd.read_csv(input_file, sep='\t', header=None, names=['Ticker', 'Company', 'Sector', 'AUM'])

print(f"Loaded {len(df)} ETFs from etfcsv.csv")
print()

# Keep only the columns we need: Ticker, Company, Sector
df_formatted = df[['Ticker', 'Company', 'Sector']].copy()

# Remove any rows with missing tickers
df_formatted = df_formatted.dropna(subset=['Ticker'])

# Clean up ticker symbols (remove any whitespace)
df_formatted['Ticker'] = df_formatted['Ticker'].str.strip()

# Sort by ticker
df_formatted = df_formatted.sort_values('Ticker')

# Save to CSV with same format as 5000.csv
df_formatted.to_csv(output_file, index=False)

print(f"✓ Successfully reformatted {len(df_formatted)} ETFs")
print(f"✓ Saved to: {output_file}")
print()
print("Format matches 5000.csv:")
print("  - Header: Ticker,Company,Sector")
print("  - Sorted by ticker symbol")
print()

# Show first few rows
print("First 10 rows:")
print("-" * 80)
print(df_formatted.head(10).to_string(index=False))
print()

print("=" * 80)
print("COMPLETE!")
print("=" * 80)
