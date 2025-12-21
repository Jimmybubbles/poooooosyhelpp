import pandas as pd
import os
from datetime import datetime

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Output file path
output_file = os.path.join(script_dir, 'CSV', 'ASX_stocks.csv')

# Comprehensive ASX stock list (ASX 200 + additional stocks and ETFs)
asx_stocks = [
    {'Ticker': 'A2M', 'Company': 'The a2 Milk Company Ltd'},
    {'Ticker': 'AAA', 'Company': 'Betashares Australian High Interest Cash ETF'},
    {'Ticker': 'ABC', 'Company': 'Adbri Ltd'},
    {'Ticker': 'ABP', 'Company': 'Abacus Property Group'},
    {'Ticker': 'AFI', 'Company': 'Australian Foundation Investment Company Ltd'},
    {'Ticker': 'AGL', 'Company': 'AGL Energy Ltd'},
    {'Ticker': 'AIA', 'Company': 'Auckland International Airport Ltd'},
    {'Ticker': 'ALD', 'Company': 'Ampol Ltd'},
    {'Ticker': 'ALL', 'Company': 'Aristocrat Leisure Ltd'},
    {'Ticker': 'ALQ', 'Company': 'Als Ltd'},
    {'Ticker': 'ALU', 'Company': 'Altium Ltd'},
    {'Ticker': 'ALX', 'Company': 'Atlas Arteria'},
    {'Ticker': 'AMC', 'Company': 'Amcor Plc'},
    {'Ticker': 'AMP', 'Company': 'AMP Ltd'},
    {'Ticker': 'ANN', 'Company': 'Ansell Ltd'},
    {'Ticker': 'ANZ', 'Company': 'Australia and New Zealand Banking Group Ltd'},
    {'Ticker': 'APA', 'Company': 'APA Group'},
    {'Ticker': 'APE', 'Company': 'Eagers Automotive Ltd'},
    {'Ticker': 'APT', 'Company': 'Afterpay Ltd'},
    {'Ticker': 'APX', 'Company': 'Appen Ltd'},
    {'Ticker': 'ARB', 'Company': 'ARB Corporation Ltd'},
    {'Ticker': 'ARG', 'Company': 'Argo Investments Ltd'},
    {'Ticker': 'AST', 'Company': 'Ausnet Services Ltd'},
    {'Ticker': 'ASX', 'Company': 'ASX Ltd'},
    {'Ticker': 'AWC', 'Company': 'Alumina Ltd'},
    {'Ticker': 'AZJ', 'Company': 'Aurizon Holdings Ltd'},
    {'Ticker': 'BAP', 'Company': 'Bapcor Ltd'},
    {'Ticker': 'BEN', 'Company': 'Bendigo and Adelaide Bank Ltd'},
    {'Ticker': 'BGA', 'Company': 'Bega Cheese Ltd'},
    {'Ticker': 'BHP', 'Company': 'BHP Group Ltd'},
    {'Ticker': 'BIN', 'Company': 'Bingo Industries Ltd'},
    {'Ticker': 'BKW', 'Company': 'Brickworks Ltd'},
    {'Ticker': 'BLD', 'Company': 'Boral Ltd'},
    {'Ticker': 'BOQ', 'Company': 'Bank of Queensland Ltd'},
    {'Ticker': 'BPT', 'Company': 'Beach Energy Ltd'},
    {'Ticker': 'BRG', 'Company': 'Breville Group Ltd'},
    {'Ticker': 'BSL', 'Company': 'Bluescope Steel Ltd'},
    {'Ticker': 'BWP', 'Company': 'BWP Trust'},
    {'Ticker': 'BXB', 'Company': 'Brambles Ltd'},
    {'Ticker': 'CAR', 'Company': 'Carsales.com Ltd'},
    {'Ticker': 'CBA', 'Company': 'Commonwealth Bank of Australia'},
    {'Ticker': 'CCL', 'Company': 'Coca-Cola Amatil Ltd'},
    {'Ticker': 'CCP', 'Company': 'Credit Corp Group Ltd'},
    {'Ticker': 'CDA', 'Company': 'Codan Ltd'},
    {'Ticker': 'CGF', 'Company': 'Challenger Ltd'},
    {'Ticker': 'CHC', 'Company': 'Charter Hall Group'},
    {'Ticker': 'CHN', 'Company': 'Chalice Mining Ltd'},
    {'Ticker': 'CIA', 'Company': 'Champion Iron Ltd'},
    {'Ticker': 'CIM', 'Company': 'Cimic Group Ltd'},
    {'Ticker': 'CLW', 'Company': 'Charter Hall Long Wale REIT'},
    {'Ticker': 'CMW', 'Company': 'Cromwell Property Group'},
    {'Ticker': 'CNU', 'Company': 'Chorus Ltd'},
    {'Ticker': 'COH', 'Company': 'Cochlear Ltd'},
    {'Ticker': 'COL', 'Company': 'Coles Group Ltd'},
    {'Ticker': 'CPU', 'Company': 'Computershare Ltd'},
    {'Ticker': 'CQR', 'Company': 'Charter Hall Retail REIT'},
    {'Ticker': 'CSL', 'Company': 'CSL Ltd'},
    {'Ticker': 'CSR', 'Company': 'CSR Ltd'},
    {'Ticker': 'CTD', 'Company': 'Corporate Travel Management Ltd'},
    {'Ticker': 'CWN', 'Company': 'Crown Resorts Ltd'},
    {'Ticker': 'CWY', 'Company': 'Cleanaway Waste Management Ltd'},
    {'Ticker': 'DEG', 'Company': 'De Grey Mining Ltd'},
    {'Ticker': 'DHG', 'Company': 'Domain Holdings Australia Ltd'},
    {'Ticker': 'DMP', 'Company': 'Domino\'s PIZZA Enterprises Ltd'},
    {'Ticker': 'DOW', 'Company': 'Downer Edi Ltd'},
    {'Ticker': 'DRR', 'Company': 'Deterra Royalties Ltd'},
    {'Ticker': 'DXS', 'Company': 'Dexus'},
    {'Ticker': 'EBO', 'Company': 'Ebos Group Ltd'},
    {'Ticker': 'ELD', 'Company': 'Elders Ltd'},
    {'Ticker': 'EML', 'Company': 'EML Payments Ltd'},
    {'Ticker': 'EVN', 'Company': 'Evolution Mining Ltd'},
    {'Ticker': 'EVT', 'Company': 'Event Hospitality and Entertainment Ltd'},
    {'Ticker': 'FBU', 'Company': 'Fletcher Building Ltd'},
    {'Ticker': 'FLT', 'Company': 'Flight Centre Travel Group Ltd'},
    {'Ticker': 'FMG', 'Company': 'Fortescue Metals Group Ltd'},
    {'Ticker': 'FPH', 'Company': 'Fisher & Paykel Healthcare Corporation Ltd'},
    {'Ticker': 'GMG', 'Company': 'Goodman Group'},
    {'Ticker': 'GNE', 'Company': 'Genesis Energy Ltd'},
    {'Ticker': 'GOZ', 'Company': 'Growthpoint Properties Australia'},
    {'Ticker': 'GPT', 'Company': 'GPT Group'},
    {'Ticker': 'GXY', 'Company': 'Galaxy Resources Ltd'},
    {'Ticker': 'HLS', 'Company': 'Healius Ltd'},
    {'Ticker': 'HVN', 'Company': 'Harvey Norman Holdings Ltd'},
    {'Ticker': 'IAG', 'Company': 'Insurance Australia Group Ltd'},
    {'Ticker': 'IEL', 'Company': 'Idp Education Ltd'},
    {'Ticker': 'IFL', 'Company': 'IOOF Holdings Ltd'},
    {'Ticker': 'IFT', 'Company': 'Infratil Ltd'},
    {'Ticker': 'IGO', 'Company': 'IGO Ltd'},
    {'Ticker': 'ILU', 'Company': 'Iluka Resources Ltd'},
    {'Ticker': 'IOO', 'Company': 'Ishares Global 100 ETF'},
    {'Ticker': 'IOZ', 'Company': 'Ishares Core S&P/ASX 200 ETF'},
    {'Ticker': 'IPL', 'Company': 'Incitec Pivot Ltd'},
    {'Ticker': 'IRE', 'Company': 'Iress Ltd'},
    {'Ticker': 'IVV', 'Company': 'Ishares S&P 500 ETF'},
    {'Ticker': 'JBH', 'Company': 'JB Hi-Fi Ltd'},
    {'Ticker': 'JHX', 'Company': 'James Hardie Industries Plc'},
    {'Ticker': 'LFG', 'Company': 'Liberty Financial Group'},
    {'Ticker': 'LFS', 'Company': 'Latitude Group Holdings Ltd'},
    {'Ticker': 'LLC', 'Company': 'Lendlease Group'},
    {'Ticker': 'LNK', 'Company': 'Link Administration Holdings Ltd'},
    {'Ticker': 'LYC', 'Company': 'Lynas Rare EARTHS Ltd'},
    {'Ticker': 'MCY', 'Company': 'Mercury NZ Ltd'},
    {'Ticker': 'MEZ', 'Company': 'Meridian Energy Ltd'},
    {'Ticker': 'MFG', 'Company': 'Magellan Financial Group Ltd'},
    {'Ticker': 'MGR', 'Company': 'Mirvac Group'},
    {'Ticker': 'MIN', 'Company': 'Mineral Resources Ltd'},
    {'Ticker': 'MLT', 'Company': 'Milton Corporation Ltd'},
    {'Ticker': 'MP1', 'Company': 'Megaport Ltd'},
    {'Ticker': 'MPL', 'Company': 'Medibank Private Ltd'},
    {'Ticker': 'MQG', 'Company': 'Macquarie Group Ltd'},
    {'Ticker': 'MTS', 'Company': 'Metcash Ltd'},
    {'Ticker': 'NAB', 'Company': 'National Australia Bank Ltd'},
    {'Ticker': 'NCM', 'Company': 'Newcrest Mining Ltd'},
    {'Ticker': 'NEC', 'Company': 'Nine Entertainment Co. Holdings Ltd'},
    {'Ticker': 'NHF', 'Company': 'Nib Holdings Ltd'},
    {'Ticker': 'NIC', 'Company': 'Nickel Mines Ltd'},
    {'Ticker': 'NSR', 'Company': 'National Storage REIT'},
    {'Ticker': 'NST', 'Company': 'Northern Star Resources Ltd'},
    {'Ticker': 'NUF', 'Company': 'Nufarm Ltd'},
    {'Ticker': 'NWL', 'Company': 'Netwealth Group Ltd'},
    {'Ticker': 'NXT', 'Company': 'NEXTDC Ltd'},
    {'Ticker': 'ORA', 'Company': 'Orora Ltd'},
    {'Ticker': 'ORE', 'Company': 'Orocobre Ltd'},
    {'Ticker': 'ORG', 'Company': 'Origin Energy Ltd'},
    {'Ticker': 'ORI', 'Company': 'Orica Ltd'},
    {'Ticker': 'OSH', 'Company': 'Oil Search Ltd'},
    {'Ticker': 'OZL', 'Company': 'OZ Minerals Ltd'},
    {'Ticker': 'PBH', 'Company': 'Pointsbet Holdings Ltd'},
    {'Ticker': 'PDL', 'Company': 'Pendal Group Ltd'},
    {'Ticker': 'PLS', 'Company': 'Pilbara Minerals Ltd'},
    {'Ticker': 'PME', 'Company': 'Pro Medicus Ltd'},
    {'Ticker': 'PMV', 'Company': 'Premier Investments Ltd'},
    {'Ticker': 'PNI', 'Company': 'Pinnacle Investment Management Group Ltd'},
    {'Ticker': 'PNV', 'Company': 'Polynovo Ltd'},
    {'Ticker': 'PPT', 'Company': 'Perpetual Ltd'},
    {'Ticker': 'PTM', 'Company': 'Platinum Asset Management Ltd'},
    {'Ticker': 'QAN', 'Company': 'Qantas Airways Ltd'},
    {'Ticker': 'QBE', 'Company': 'QBE Insurance Group Ltd'},
    {'Ticker': 'QUB', 'Company': 'QUBE Holdings Ltd'},
    {'Ticker': 'REA', 'Company': 'REA Group Ltd'},
    {'Ticker': 'REH', 'Company': 'Reece Ltd'},
    {'Ticker': 'RHC', 'Company': 'Ramsay Health Care Ltd'},
    {'Ticker': 'RIO', 'Company': 'RIO Tinto Ltd'},
    {'Ticker': 'RMD', 'Company': 'Resmed Inc'},
    {'Ticker': 'RRL', 'Company': 'Regis Resources Ltd'},
    {'Ticker': 'RWC', 'Company': 'Reliance Worldwide Corporation Ltd'},
    {'Ticker': 'S32', 'Company': 'SOUTH32 Ltd'},
    {'Ticker': 'SCG', 'Company': 'Scentre Group'},
    {'Ticker': 'SCP', 'Company': 'Shopping Centres Australasia Property Group'},
    {'Ticker': 'SDF', 'Company': 'Steadfast Group Ltd'},
    {'Ticker': 'SEK', 'Company': 'Seek Ltd'},
    {'Ticker': 'SGM', 'Company': 'Sims Ltd'},
    {'Ticker': 'SGP', 'Company': 'Stockland'},
    {'Ticker': 'SGR', 'Company': 'The Star Entertainment Group Ltd'},
    {'Ticker': 'SHL', 'Company': 'Sonic Healthcare Ltd'},
    {'Ticker': 'SKC', 'Company': 'Skycity Entertainment Group Ltd'},
    {'Ticker': 'SKI', 'Company': 'Spark Infrastructure Group'},
    {'Ticker': 'SLK', 'Company': 'Sealink Travel Group Ltd'},
    {'Ticker': 'SNZ', 'Company': 'Summerset Group Holdings Ltd'},
    {'Ticker': 'SOL', 'Company': 'Washington H Soul Pattinson & Company Ltd'},
    {'Ticker': 'SPK', 'Company': 'Spark New Zealand Ltd'},
    {'Ticker': 'STO', 'Company': 'Santos Ltd'},
    {'Ticker': 'STW', 'Company': 'SPDR S&P/ASX 200 Fund'},
    {'Ticker': 'SUL', 'Company': 'Super Retail Group Ltd'},
    {'Ticker': 'SUN', 'Company': 'Suncorp Group Ltd'},
    {'Ticker': 'SVW', 'Company': 'Seven Group Holdings Ltd'},
    {'Ticker': 'SYD', 'Company': 'Sydney Airport'},
    {'Ticker': 'TAH', 'Company': 'Tabcorp Holdings Ltd'},
    {'Ticker': 'TCL', 'Company': 'Transurban Group'},
    {'Ticker': 'TLS', 'Company': 'Telstra Corporation Ltd'},
    {'Ticker': 'TLT', 'Company': 'Tilt Renewables Ltd'},
    {'Ticker': 'TNE', 'Company': 'Technology One Ltd'},
    {'Ticker': 'TPG', 'Company': 'TPG Telecom Ltd'},
    {'Ticker': 'TWE', 'Company': 'Treasury Wine Estates Ltd'},
    {'Ticker': 'TYR', 'Company': 'Tyro Payments Ltd'},
    {'Ticker': 'VAP', 'Company': 'Vanguard Australian Property Securities INDEX ETF'},
    {'Ticker': 'VAS', 'Company': 'Vanguard Australian Shares INDEX ETF'},
    {'Ticker': 'VCX', 'Company': 'Vicinity Centres'},
    {'Ticker': 'VEA', 'Company': 'Viva Energy Group Ltd'},
    {'Ticker': 'VEU', 'Company': 'Vanguard All-World Ex-US Shares INDEX ETF'},
    {'Ticker': 'VGS', 'Company': 'Vanguard MSCI INDEX International Shares ETF'},
    {'Ticker': 'VOC', 'Company': 'Vocus Group Ltd'},
    {'Ticker': 'VTS', 'Company': 'Vanguard US Total Market Shares INDEX ETF'},
    {'Ticker': 'VUK', 'Company': 'Virgin Money Uk Plc'},
    {'Ticker': 'WAM', 'Company': 'WAM Capital Ltd'},
    {'Ticker': 'WBC', 'Company': 'Westpac Banking Corporation'},
    {'Ticker': 'WEB', 'Company': 'Webjet Ltd'},
    {'Ticker': 'WES', 'Company': 'Wesfarmers Ltd'},
    {'Ticker': 'WOR', 'Company': 'Worley Ltd'},
    {'Ticker': 'WOW', 'Company': 'Woolworths Group Ltd'},
    {'Ticker': 'WPL', 'Company': 'Woodside Petroleum Ltd'},
    {'Ticker': 'WPR', 'Company': 'Waypoint REIT'},
    {'Ticker': 'WTC', 'Company': 'Wisetech Global Ltd'},
    {'Ticker': 'XRO', 'Company': 'Xero Ltd'},
    {'Ticker': 'YAL', 'Company': 'Yancoal Australia Ltd'},
    {'Ticker': 'Z1P', 'Company': 'ZIP Co Ltd'},
    {'Ticker': 'ZIM', 'Company': 'Zimplats Holdings Ltd'},

    # Additional popular ETFs
    {'Ticker': 'A200', 'Company': 'BetaShares Australia 200 ETF'},
    {'Ticker': 'VDHG', 'Company': 'Vanguard Diversified High Growth Index ETF'},
    {'Ticker': 'DHHF', 'Company': 'BetaShares Diversified All Growth ETF'},
    {'Ticker': 'NDQ', 'Company': 'BetaShares NASDAQ 100 ETF'},
    {'Ticker': 'VHY', 'Company': 'Vanguard Australian Shares High Yield ETF'},
    {'Ticker': 'VGB', 'Company': 'Vanguard Australian Government Bond Index ETF'},
    {'Ticker': 'VAF', 'Company': 'Vanguard Australian Fixed Interest Index ETF'},
    {'Ticker': 'VGE', 'Company': 'Vanguard FTSE Emerging Markets Shares ETF'},
    {'Ticker': 'GOLD', 'Company': 'ETFS Physical Gold'},
    {'Ticker': 'QAU', 'Company': 'BetaShares Gold Bullion ETF - Currency Hedged'},
    {'Ticker': 'BBOZ', 'Company': 'BetaShares Australian Equities Strong Bear'},
    {'Ticker': 'BEAR', 'Company': 'BetaShares Australian Equities Bear'},
    {'Ticker': 'YMAX', 'Company': 'BetaShares S&P 500 Yield Maximiser Fund'},
    {'Ticker': 'HACK', 'Company': 'BetaShares Global Cybersecurity ETF'},
    {'Ticker': 'ASIA', 'Company': 'BetaShares Asia Technology Tigers ETF'},
    {'Ticker': 'ETHI', 'Company': 'BetaShares Global Sustainability Leaders ETF'},
]

def main():
    print("=" * 80)
    print("CREATING ASX STOCK LIST")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Create DataFrame
    df = pd.DataFrame(asx_stocks)

    # Remove duplicates
    df = df.drop_duplicates(subset=['Ticker'])

    # Sort by ticker
    df = df.sort_values('Ticker').reset_index(drop=True)

    # Add Sector column (will be filled with "Unknown" for now)
    df['Sector'] = 'Unknown'

    # Reorder columns
    df = df[['Ticker', 'Company', 'Sector']]

    # Save to CSV
    df.to_csv(output_file, index=False)

    print(f"Total tickers: {len(df)}")
    print(f"File saved to: {output_file}")
    print()
    print("Sample of stocks:")
    print(df.head(20).to_string(index=False))
    print()
    print("IMPORTANT NOTES:")
    print("=" * 80)
    print("1. ASX tickers need .AX suffix for yfinance")
    print("   Example: BHP.AX, CBA.AX, CSL.AX")
    print()
    print("2. To use with your scanners, you'll need to:")
    print("   - Create ASX-specific scanner scripts")
    print("   - Modify ticker handling to add .AX suffix")
    print("   - Consider timezone differences (AEDT/AEST)")
    print()
    print("3. File structure created:")
    print(f"   {output_file}")
    print()
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
