"""
Reformat ASXListedCompanies.csv to match 5000.csv format
"""

import pandas as pd

# Read the ASX file, skipping the first 2 rows (header with date and blank line)
df = pd.read_csv('ASXListedCompanies.csv', skiprows=2)

# Current columns: 'Company name', 'ASX code', 'GICS industry group'
# Rename to match 5000.csv format: 'Ticker', 'Company', 'Sector'
df.columns = ['Company', 'Ticker', 'Sector']

# Reorder columns to: Ticker, Company, Sector
df = df[['Ticker', 'Company', 'Sector']]

# Remove quotes from all fields
df = df.apply(lambda x: x.str.strip('"') if x.dtype == "object" else x)

# Save the reformatted file
df.to_csv('ASXListedCompanies.csv', index=False)

print(f"Reformatted {len(df)} ASX companies")
print("\nFirst 10 rows:")
print(df.head(10).to_string(index=False))
print("\nFile saved as ASXListedCompanies.csv")
