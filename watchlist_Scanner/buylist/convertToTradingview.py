# Dictionary mapping tickers to their exchanges. Note: You might need to adjust these based on the most current listing
ticker_exchange = {
    "WWR": "NASDAQ",
    "BFLY": "NYSE",
    "CLIR": "NASDAQ",
    "EAST": "NASDAQ",
    "MBOT": "NASDAQ",
    "FEAM": "NASDAQ",
    "VERI": "NASDAQ",
    "GSAT": "NYSE",
    "QSI": "NASDAQ",
    "LIDR": "NASDAQ",
    "NRGV": "NASDAQ",
    "VOR": "NYSE",
    "NEON": "NASDAQ",
    "XERS": "NASDAQ",
    "VYNE": "NASDAQ",
    "ZDGE": "NASDAQ",
    "SWIM": "NYSE",
    "FBIO": "NASDAQ",
    "APYX": "NASDAQ",
    "WGS": "NASDAQ",
    "LSTA": "NASDAQ",
    "BLDE": "NASDAQ",
    "REKR": "NASDAQ",
    "FTK": "NYSE",
    "POAI": "NASDAQ",
    "PTN": "NASDAQ",
    "STEM": "NYSE",
    "PRLD": "NASDAQ",
    "VMEO": "NASDAQ",
    "DXLG": "NASDAQ",
    "SPWH": "NASDAQ",
    "HLLY": "NYSE",
    "ORGS": "NASDAQ",
    "LOAN": "NASDAQ",
    "AEVA": "NYSE",
    "SLRX": "NASDAQ",
    "PTON": "NASDAQ",
    "WVVI": "NASDAQ",
    "JOBY": "NYSE",
    "APPS": "NASDAQ",
    "QS": "NYSE",
    "OGEN": "NASDAQ",
    "KALA": "NASDAQ",
    "ADTN": "NASDAQ",
    "STRM": "NASDAQ",
    "IPWR": "NASDAQ",
    "EGAN": "NASDAQ",
    "PRSO": "NASDAQ",
    "CMTL": "NASDAQ",
    "RXRX": "NASDAQ",
    "OSPN": "NASDAQ",
    "FUSB": "NASDAQ",
    "ELMD": "NASDAQ",
    "ATRA": "NASDAQ",
    "LQDA": "NASDAQ",
    "EVER": "NASDAQ",
    "ENVX": "NASDAQ",
    "SOC": "NYSE",
    "BOTJ": "NASDAQ",
    "QNST": "NASDAQ",
    "RCEL": "NASDAQ",
    "GRPN": "NASDAQ",
    "ACVA": "NYSE",
    "DVAX": "NASDAQ",
    "CXW": "NYSE",
    "SHLS": "NYSE",
    "EE": "NYSE",
    "BLFS": "NASDAQ",
    "TGI": "NYSE",
    "XRX": "NYSE",
    "LMND": "NYSE",
    "PDEX": "NASDAQ",
    "GHM": "NYSE",
    "M": "NYSE",
    "CPHC": "NASDAQ",
    "MNTS": "NASDAQ",
    "MEI": "NYSE",
    "AUBN": "NASDAQ",
    "AR": "NYSE",
    "RAPT": "NASDAQ",
    "PRAX": "NASDAQ",
    "USD": "NYSE",
    "UGI": "NYSE",
    "COCO": "NASDAQ",
    "BBSI": "NASDAQ",
    "ALGM": "NASDAQ",
    "PFE": "NYSE",
    "PRIM": "NASDAQ",
    "MRCY": "NASDAQ",
    "VCEL": "NASDAQ",
    "BBIO": "NASDAQ",
    "KRC": "NYSE",
    "JEF": "NYSE",
    "QTWO": "NASDAQ",
    "OPY": "NYSE",
    "TGLS": "NYSE",
    "BKE": "NYSE",
    "CSCO": "NASDAQ",
    "ETR": "NYSE",
    "GMED": "NYSE",
    "C": "NYSE",
    "BSX": "NYSE",
    "IRON": "NYSE",
    "ATGE": "NYSE",
    "BELFB": "NASDAQ",
    "FOUR": "NYSE",
    "NVEC": "NASDAQ",
    "STT": "NYSE",
    "APTV": "NYSE",
    "TW": "NYSE",
    "HCI": "NYSE",
    "ARES": "NYSE",
    "GL": "NYSE",
    "TTWO": "NASDAQ",
    "AXP": "NYSE",
    "BURL": "NYSE",
    "HON": "NYSE",
    "MTN": "NYSE",
    "GPI": "NYSE",
    "DDS": "NYSE",
    "MA": "NYSE",
    "FDS": "NYSE",
    "BLK": "NYSE",
    "MKL": "NYSE",
    "AZO": "NYSE"
}

def convert_to_tradingview_list(tickers, output_filename="tradingview_list.txt"):
    with open(output_filename, 'w') as file:
        for ticker in tickers:
            exchange = ticker_exchange.get(ticker, "UNKNOWN")
            file.write(f"{exchange}:{ticker}\n")
    
    print(f"List of tickers has been saved to {output_filename}")

# Extract tickers from the input
tickers = [line.split()[1] for line in """BUY WWR 12/26/2024 : Upside Breakout 0.57
BUY BFLY 12/26/2024 : Upside Breakout 1.02
BUY CLIR 12/26/2024 : Upside Breakout 1.1
BUY EAST 12/23/2024 : Upside Breakout 1.16
BUY MBOT 12/26/2024 : Upside Breakout 1.39
BUY FEAM 12/26/2024 : Upside Breakout 1.4
BUY VERI 12/26/2024 : Upside Breakout 1.71
BUY GSAT 12/25/2024 : Upside Breakout 1.86
BUY QSI 12/25/2024 : Upside Breakout 1.89
BUY LIDR 12/26/2024 : Upside Breakout 2.02
BUY NRGV 12/25/2024 : Upside Breakout 2.02
BUY VOR 12/26/2024 : Upside Breakout 2.1
BUY NEON 12/25/2024 : Upside Breakout 2.13
BUY XERS 12/23/2024 : Upside Breakout 2.24
BUY VYNE 12/25/2024 : Upside Breakout 2.31
BUY ZDGE 12/26/2024 : Upside Breakout 2.31
BUY SWIM 12/25/2024 : Upside Breakout 2.45
BUY FBIO 12/26/2024 : Upside Breakout 2.48
BUY APYX 12/23/2024 : Upside Breakout 2.67
BUY WGS 12/25/2024 : Upside Breakout 2.79
BUY LSTA 12/23/2024 : Upside Breakout 2.8
BUY BLDE 12/25/2024 : Upside Breakout 3.14
BUY REKR 12/26/2024 : Upside Breakout 3.27
BUY FTK 12/25/2024 : Upside Breakout 3.38
BUY POAI 12/26/2024 : Upside Breakout 3.38
BUY PTN 12/26/2024 : Upside Breakout 3.45
BUY STEM 12/26/2024 : Upside Breakout 3.48
BUY PRLD 12/25/2024 : Upside Breakout 3.78
BUY VMEO 12/23/2024 : Upside Breakout 3.8
BUY DXLG 12/25/2024 : Upside Breakout 4.08
BUY SPWH 12/26/2024 : Upside Breakout 4.44
BUY HLLY 12/26/2024 : Upside Breakout 4.58
BUY ORGS 12/23/2024 : Upside Breakout 4.7
BUY LOAN 12/25/2024 : Upside Breakout 4.76
BUY AEVA 12/25/2024 : Upside Breakout 5.05
BUY SLRX 12/26/2024 : Upside Breakout 5.112
BUY PTON 12/25/2024 : Upside Breakout 5.38
BUY WVVI 12/25/2024 : Upside Breakout 5.39
BUY JOBY 12/23/2024 : Upside Breakout 5.98
BUY APPS 12/25/2024 : Upside Breakout 6.32
BUY QS 12/25/2024 : Upside Breakout 6.5
BUY OGEN 12/26/2024 : Upside Breakout 6.84
BUY KALA 12/26/2024 : Upside Breakout 7.12
BUY ADTN 12/25/2024 : Upside Breakout 7.14
BUY STRM 12/25/2024 : Upside Breakout 7.35
BUY IPWR 12/25/2024 : Upside Breakout 7.745
BUY EGAN 12/25/2024 : Upside Breakout 8.01
BUY PRSO 12/26/2024 : Upside Breakout 8.03
BUY CMTL 12/23/2024 : Upside Breakout 8.61
BUY RXRX 12/26/2024 : Upside Breakout 9.69
BUY OSPN 12/25/2024 : Upside Breakout 10.33
BUY FUSB 12/26/2024 : Upside Breakout 10.48
BUY ELMD 12/25/2024 : Upside Breakout 10.72
BUY ATRA 12/23/2024 : Upside Breakout 11.0
BUY LQDA 12/23/2024 : Upside Breakout 11.35
BUY EVER 12/26/2024 : Upside Breakout 11.61
BUY ENVX 12/25/2024 : Upside Breakout 11.72
BUY SOC 12/25/2024 : Upside Breakout 11.89
BUY BOTJ 12/25/2024 : Upside Breakout 12.21
BUY QNST 12/25/2024 : Upside Breakout 12.45
BUY RCEL 12/26/2024 : Upside Breakout 12.64
BUY GRPN 12/23/2024 : Upside Breakout 12.65
BUY ACVA 12/25/2024 : Upside Breakout 14.34
BUY DVAX 12/25/2024 : Upside Breakout 14.42
BUY CXW 12/25/2024 : Upside Breakout 14.56
BUY SHLS 12/23/2024 : Upside Breakout 14.68
BUY EE 12/23/2024 : Upside Breakout 15.01
BUY BLFS 12/25/2024 : Upside Breakout 15.35
BUY TGI 12/25/2024 : Upside Breakout 15.43
BUY XRX 12/26/2024 : Upside Breakout 15.84
BUY LMND 12/25/2024 : Upside Breakout 16.22
BUY PDEX 12/26/2024 : Upside Breakout 18.32
BUY GHM 12/25/2024 : Upside Breakout 18.86
BUY M 12/23/2024 : Upside Breakout 18.94
BUY CPHC 12/23/2024 : Upside Breakout 20.54
BUY MNTS 12/26/2024 : Upside Breakout 21.0
BUY MEI 12/26/2024 : Upside Breakout 21.04
BUY AUBN 12/23/2024 : Upside Breakout 21.24
BUY AR 12/23/2024 : Upside Breakout 22.77
BUY RAPT 12/23/2024 : Upside Breakout 23.32
BUY PRAX 12/23/2024 : Upside Breakout 24.0
BUY USD 12/25/2024 : Upside Breakout 24.5
BUY UGI 12/25/2024 : Upside Breakout 24.77
BUY COCO 12/25/2024 : Upside Breakout 25.21
BUY BBSI 12/23/2024 : Upside Breakout 27.897
BUY ALGM 12/25/2024 : Upside Breakout 29.01
BUY PFE 12/23/2024 : Upside Breakout 29.73
BUY PRIM 12/25/2024 : Upside Breakout 31.64
BUY MRCY 12/23/2024 : Upside Breakout 32.98
BUY VCEL 12/23/2024 : Upside Breakout 33.87
BUY BBIO 12/23/2024 : Upside Breakout 37.85
BUY KRC 12/25/2024 : Upside Breakout 38.71
BUY JEF 12/23/2024 : Upside Breakout 39.87
BUY QTWO 12/25/2024 : Upside Breakout 40.18
BUY OPY 12/23/2024 : Upside Breakout 40.66
BUY TGLS 12/25/2024 : Upside Breakout 42.78
BUY BKE 12/25/2024 : Upside Breakout 45.89
BUY CSCO 12/23/2024 : Upside Breakout 50.51
BUY ETR 12/23/2024 : Upside Breakout 51.535
BUY GMED 12/25/2024 : Upside Breakout 51.93
BUY C 12/26/2024 : Upside Breakout 53.64
BUY BSX 12/25/2024 : Upside Breakout 57.6
BUY IRON 12/23/2024 : Upside Breakout 59.5
BUY ATGE 12/25/2024 : Upside Breakout 59.61
BUY BELFB 12/25/2024 : Upside Breakout 62.9
BUY FOUR 12/25/2024 : Upside Breakout 70.6
BUY NVEC 12/23/2024 : Upside Breakout 74.03
BUY STT 12/25/2024 : Upside Breakout 77.3
BUY APTV 12/23/2024 : Upside Breakout 84.49
BUY TW 12/25/2024 : Upside Breakout 88.97
BUY HCI 12/26/2024 : Upside Breakout 93.18
BUY ARES 12/23/2024 : Upside Breakout 115.56
BUY GL 12/23/2024 : Upside Breakout 121.68
BUY TTWO 12/25/2024 : Upside Breakout 158.4
BUY AXP 12/23/2024 : Upside Breakout 186.32
BUY BURL 12/25/2024 : Upside Breakout 187.85
BUY HON 12/25/2024 : Upside Breakout 204.53
BUY MTN 12/23/2024 : Upside Breakout 206.9
BUY GPI 12/25/2024 : Upside Breakout 287.45
BUY DDS 12/23/2024 : Upside Breakout 381.44
BUY MA 12/23/2024 : Upside Breakout 418.77
BUY FDS 12/23/2024 : Upside Breakout 454.72
BUY BLK 12/25/2024 : Upside Breakout 784.15
BUY MKL 12/23/2024 : Upside Breakout 1428.39
BUY AZO 12/23/2024 : Upside Breakout 2567.59""".split('\n')]

# Call the function to create the TradingView list
convert_to_tradingview_list(tickers)