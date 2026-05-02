import pandas as pd
import yfinance as yf
import os
from datetime import datetime
import time

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Output file path
output_file = os.path.join(script_dir, 'CSV', 'ASX_stocks.csv')

def get_asx_stocks():
    """
    Fetch ASX stock list from Wikipedia and other sources
    ASX tickers need .AX suffix for yfinance
    """
    print("=" * 80)
    print("FETCHING ASX STOCKS AND ETFs")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Try to get ASX 200 from Wikipedia
    print("Fetching ASX 200 stocks from Wikipedia...")
    try:
        url = 'https://en.wikipedia.org/wiki/S%26P/ASX_200'
        tables = pd.read_html(url)

        # Find the table with stock listings
        asx200_df = None
        for table in tables:
            if 'Code' in table.columns or 'ASX code' in table.columns:
                asx200_df = table
                break

        if asx200_df is not None:
            # Clean up the dataframe
            if 'Code' in asx200_df.columns:
                asx200_df = asx200_df[['Code', 'Company']]
                asx200_df.columns = ['Ticker', 'Company']
            elif 'ASX code' in asx200_df.columns:
                asx200_df = asx200_df[['ASX code', 'Company']]
                asx200_df.columns = ['Ticker', 'Company']

            print(f"Found {len(asx200_df)} ASX 200 stocks")
        else:
            print("Could not parse ASX 200 table from Wikipedia")
            asx200_df = pd.DataFrame()
    except Exception as e:
        print(f"Error fetching ASX 200: {e}")
        asx200_df = pd.DataFrame()

    # Try to get ASX 300 from Wikipedia
    print("\nFetching ASX 300 stocks from Wikipedia...")
    try:
        url = 'https://en.wikipedia.org/wiki/S%26P/ASX_300'
        tables = pd.read_html(url)

        # Find the table with stock listings
        asx300_df = None
        for table in tables:
            if 'Code' in table.columns or 'ASX code' in table.columns:
                asx300_df = table
                break

        if asx300_df is not None:
            # Clean up the dataframe
            if 'Code' in asx300_df.columns:
                asx300_df = asx300_df[['Code', 'Company']]
                asx300_df.columns = ['Ticker', 'Company']
            elif 'ASX code' in asx300_df.columns:
                asx300_df = asx300_df[['ASX code', 'Company']]
                asx300_df.columns = ['Ticker', 'Company']

            print(f"Found {len(asx300_df)} ASX 300 stocks")
        else:
            print("Could not parse ASX 300 table from Wikipedia")
            asx300_df = pd.DataFrame()
    except Exception as e:
        print(f"Error fetching ASX 300: {e}")
        asx300_df = pd.DataFrame()

    # Combine ASX 200 and ASX 300
    all_stocks = pd.concat([asx200_df, asx300_df], ignore_index=True)
    all_stocks = all_stocks.drop_duplicates(subset=['Ticker'])

    # Add common ASX ETFs manually
    print("\nAdding common ASX ETFs...")
    asx_etfs = [
        {'Ticker': 'VAS', 'Company': 'Vanguard Australian Shares Index ETF'},
        {'Ticker': 'VGS', 'Company': 'Vanguard MSCI Index International Shares ETF'},
        {'Ticker': 'VTS', 'Company': 'Vanguard US Total Market Shares Index ETF'},
        {'Ticker': 'A200', 'Company': 'BetaShares Australia 200 ETF'},
        {'Ticker': 'IOZ', 'Company': 'iShares Core S&P/ASX 200 ETF'},
        {'Ticker': 'STW', 'Company': 'SPDR S&P/ASX 200 Fund'},
        {'Ticker': 'VHY', 'Company': 'Vanguard Australian Shares High Yield ETF'},
        {'Ticker': 'VDHG', 'Company': 'Vanguard Diversified High Growth Index ETF'},
        {'Ticker': 'DHHF', 'Company': 'BetaShares Diversified All Growth ETF'},
        {'Ticker': 'NDQ', 'Company': 'BetaShares NASDAQ 100 ETF'},
        {'Ticker': 'IVV', 'Company': 'iShares S&P 500 ETF'},
        {'Ticker': 'VGE', 'Company': 'Vanguard FTSE Emerging Markets Shares ETF'},
        {'Ticker': 'VAP', 'Company': 'Vanguard Australian Property Securities Index ETF'},
        {'Ticker': 'VAF', 'Company': 'Vanguard Australian Fixed Interest Index ETF'},
        {'Ticker': 'VGB', 'Company': 'Vanguard Australian Government Bond Index ETF'},
        {'Ticker': 'GOLD', 'Company': 'ETFS Physical Gold'},
        {'Ticker': 'QAU', 'Company': 'BetaShares Gold Bullion ETF - Currency Hedged'},
        {'Ticker': 'BBOZ', 'Company': 'BetaShares Australian Equities Strong Bear'},
        {'Ticker': 'BEAR', 'Company': 'BetaShares Australian Equities Bear'},
        {'Ticker': 'YMAX', 'Company': 'BetaShares S&P 500 Yield Maximiser Fund'},
    ]

    etf_df = pd.DataFrame(asx_etfs)
    all_stocks = pd.concat([all_stocks, etf_df], ignore_index=True)
    all_stocks = all_stocks.drop_duplicates(subset=['Ticker'])

    # Add top ASX stocks manually if we didn't get many from Wikipedia
    if len(all_stocks) < 50:
        print("\nAdding top ASX stocks manually...")
        top_asx_stocks = [
            {'Ticker': 'BHP', 'Company': 'BHP Group Limited'},
            {'Ticker': 'CBA', 'Company': 'Commonwealth Bank of Australia'},
            {'Ticker': 'CSL', 'Company': 'CSL Limited'},
            {'Ticker': 'NAB', 'Company': 'National Australia Bank Limited'},
            {'Ticker': 'WBC', 'Company': 'Westpac Banking Corporation'},
            {'Ticker': 'ANZ', 'Company': 'Australia and New Zealand Banking Group'},
            {'Ticker': 'WES', 'Company': 'Wesfarmers Limited'},
            {'Ticker': 'MQG', 'Company': 'Macquarie Group Limited'},
            {'Ticker': 'WOW', 'Company': 'Woolworths Group Limited'},
            {'Ticker': 'GMG', 'Company': 'Goodman Group'},
            {'Ticker': 'RIO', 'Company': 'Rio Tinto Limited'},
            {'Ticker': 'FMG', 'Company': 'Fortescue Metals Group Ltd'},
            {'Ticker': 'TLS', 'Company': 'Telstra Corporation Limited'},
            {'Ticker': 'WDS', 'Company': 'Woodside Energy Group Ltd'},
            {'Ticker': 'TCL', 'Company': 'Transurban Group'},
            {'Ticker': 'REA', 'Company': 'REA Group Ltd'},
            {'Ticker': 'COL', 'Company': 'Coles Group Limited'},
            {'Ticker': 'QBE', 'Company': 'QBE Insurance Group Limited'},
            {'Ticker': 'STO', 'Company': 'Santos Limited'},
            {'Ticker': 'S32', 'Company': 'South32 Limited'},
        ]
        top_df = pd.DataFrame(top_asx_stocks)
        all_stocks = pd.concat([all_stocks, top_df], ignore_index=True)
        all_stocks = all_stocks.drop_duplicates(subset=['Ticker'])

    print(f"\nTotal unique tickers collected: {len(all_stocks)}")

    # Clean tickers
    all_stocks['Ticker'] = all_stocks['Ticker'].str.strip()
    all_stocks['Company'] = all_stocks['Company'].str.strip()

    # Add .AX suffix for yfinance
    all_stocks['Yahoo_Ticker'] = all_stocks['Ticker'] + '.AX'

    # Sort by ticker
    all_stocks = all_stocks.sort_values('Ticker').reset_index(drop=True)

    return all_stocks

def verify_and_get_sector(stocks_df, sample_size=50):
    """
    Verify tickers with yfinance and get sector information for a sample
    """
    print("\n" + "=" * 80)
    print("VERIFYING TICKERS AND FETCHING SECTOR INFO (Sample)")
    print("=" * 80)

    # Add sector column
    stocks_df['Sector'] = 'Unknown'

    # Sample some stocks to verify and get sector info
    sample_indices = list(range(0, len(stocks_df), max(1, len(stocks_df) // sample_size)))

    verified_count = 0
    for idx in sample_indices:
        if idx >= len(stocks_df):
            break

        ticker = stocks_df.loc[idx, 'Yahoo_Ticker']
        print(f"Verifying {ticker}...", end=' ')

        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            if 'sector' in info and info['sector']:
                stocks_df.loc[idx, 'Sector'] = info['sector']
                verified_count += 1
                print(f"OK - {info.get('sector', 'Unknown')}")
            else:
                print("OK (no sector info)")
                verified_count += 1

            time.sleep(0.2)  # Rate limiting

        except Exception as e:
            print(f"FAILED - Error: {e}")

    print(f"\nVerified {verified_count} tickers successfully")
    return stocks_df

def main():
    # Get ASX stocks
    asx_stocks = get_asx_stocks()

    # Verify a sample and get sector info
    asx_stocks = verify_and_get_sector(asx_stocks, sample_size=30)

    # Prepare final dataframe
    final_df = asx_stocks[['Ticker', 'Company', 'Sector']].copy()

    # Save to CSV
    final_df.to_csv(output_file, index=False)

    print("\n" + "=" * 80)
    print("ASX STOCK LIST GENERATION COMPLETE")
    print("=" * 80)
    print(f"Total tickers saved: {len(final_df)}")
    print(f"File saved to: {output_file}")
    print()
    print("Sample of stocks:")
    print(final_df.head(20).to_string(index=False))
    print()
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("IMPORTANT: ASX tickers need .AX suffix for yfinance")
    print("Example: BHP.AX, CBA.AX, CSL.AX")
    print()
    print("Next steps:")
    print("1. Review the generated CSV file")
    print("2. You may want to expand this list with additional ASX stocks")
    print("3. Update your scanner scripts to handle .AX ticker suffix")
    print("4. Create a new folder structure for ASX scans if needed")

if __name__ == "__main__":
    main()
