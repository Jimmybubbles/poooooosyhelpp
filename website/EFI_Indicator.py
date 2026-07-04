import pandas as pd
import numpy as np
import os
from datetime import datetime

# EFI - Faux VOL/VWAP Indicator
# Converted from Pine Script v4

class EFI_Indicator:
    """
    EFI - Faux VOL/VWAP (Elder Force Index with custom volume)

    This indicator combines:
    - Force Index calculation
    - Faux volume using ATR
    - Bollinger Bands
    - Normalized price
    """

    def __init__(self,
                 bollperiod=68,
                 signalperiod=2,
                 fiperiod=13,
                 fisf=13,
                 fi_asf_len=1,
                 mult=1.0,
                 multlow=1.0,
                 useemaforboll=True,
                 usemystdev=True,
                 atr_period=11):
        """
        Initialize indicator with parameters

        Args:
            bollperiod: Bollinger Band period (default 68)
            signalperiod: BB Basis Signal Period (default 2)
            fiperiod: Force Index EMA Period (default 13)
            fisf: Force Index Scale Factor (default 13)
            fi_asf_len: Force Index Auto-Scale Period (default 1)
            mult: BB Standard Deviation multiplier (default 1.0)
            multlow: BB Inner Standard Deviation multiplier (default 1.0)
            useemaforboll: Use EMA for BB instead of HMA (default True)
            usemystdev: Use high precision STDEV (default True)
            atr_period: ATR period for faux volume (default 11)
        """
        self.bollperiod = bollperiod
        self.signalperiod = signalperiod
        self.fiperiod = fiperiod
        self.fisf = fisf
        self.fi_asf_len = fi_asf_len
        self.mult = mult
        self.multlow = multlow
        self.useemaforboll = useemaforboll
        self.usemystdev = usemystdev
        self.atr_period = atr_period

    def calculate_atr(self, high, low, close, period):
        """Calculate Average True Range"""
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()

        return atr

    def calculate_ema(self, series, period):
        """Calculate Exponential Moving Average"""
        return series.ewm(span=period, adjust=False).mean()

    def calculate_sma(self, series, period):
        """Calculate Simple Moving Average"""
        return series.rolling(window=period).mean()

    def calculate_hma(self, series, period):
        """Calculate Hull Moving Average"""
        half_period = int(period / 2)
        sqrt_period = int(np.sqrt(period))

        wma_half = series.rolling(window=half_period).mean()
        wma_full = series.rolling(window=period).mean()

        raw_hma = 2 * wma_half - wma_full
        hma = raw_hma.rolling(window=sqrt_period).mean()

        return hma

    def calculate_stdev(self, series, period):
        """Calculate standard deviation"""
        return series.rolling(window=period).std()

    def calculate_stdev_high_precision(self, mean, src, period):
        """Calculate high precision standard deviation"""
        variance = ((src - mean) ** 2).rolling(window=period).sum() / (period - 1)
        return np.sqrt(variance)

    def calculate_bollinger_bands(self, src):
        """
        Calculate Bollinger Bands with custom precision options

        Returns:
            basis: Middle band (EMA or HMA)
            dev: Standard deviation
        """
        # Scale factor for precision (especially for crypto)
        sf = src.iloc[0] if len(src) > 0 else 1.0
        src2 = src / sf

        # Calculate mean
        if self.useemaforboll:
            mean = self.calculate_ema(src2, self.bollperiod)
        else:
            mean = self.calculate_hma(src2, self.bollperiod)

        # Calculate standard deviation
        if self.usemystdev:
            dev = self.calculate_stdev_high_precision(mean, src2, self.bollperiod)
        else:
            dev = self.calculate_stdev(src2, self.bollperiod)

        # Scale back
        basis = mean * sf
        dev = dev * sf

        return basis, dev

    def calculate_faux_volume(self, df):
        """
        Calculate faux volume using ATR

        Returns:
            vw: Volume-weighted price
        """
        close = df['Close']
        high = df['High']
        low = df['Low']

        # Calculate ATR for faux volume
        atr = self.calculate_atr(high, low, close, self.atr_period)

        # Price * Volume (using ATR as faux volume)
        price_volume = close * atr

        # Total Price Volume (sum over period 1)
        t_price_volume = price_volume

        # Faux Volume
        fake_volume = atr
        volume = fake_volume

        # Volume-weighted price
        vw = t_price_volume / volume

        return vw

    def calculate(self, df):
        """
        Calculate all indicator values

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with indicator values
        """
        close = df['Close']

        # Calculate Bollinger Bands
        basis, dev = self.calculate_bollinger_bands(close)

        # Calculate histogram (basis - signal)
        hist = basis - self.calculate_ema(basis, self.signalperiod)

        # Calculate faux volume-weighted price
        vw = self.calculate_faux_volume(df)

        # Calculate Force Index
        price_change = close - close.shift(1)
        vw_sma = self.calculate_sma(vw, self.fi_asf_len)

        forceindex = (price_change * vw / vw_sma) * self.fisf

        # Force Index EMA
        fi_ema = self.calculate_ema(forceindex, self.fiperiod)

        # Normalized Price
        normprice = close - basis

        # Bollinger Band levels
        upper_band = 0 + dev * self.mult
        lower_band = 0 - dev * self.mult
        upper_band_inner = 0 + dev * self.multlow
        lower_band_inner = 0 - dev * self.multlow

        # Determine Force Index color based on direction and momentum
        fi_change = fi_ema.diff()
        fi_color = pd.Series(index=df.index, dtype=str)

        for i in range(len(fi_ema)):
            if pd.isna(fi_ema.iloc[i]):
                fi_color.iloc[i] = 'gray'
            elif fi_ema.iloc[i] > 0:
                if not pd.isna(fi_change.iloc[i]) and fi_change.iloc[i] > 0:
                    fi_color.iloc[i] = 'lime'  # Strong bullish
                else:
                    fi_color.iloc[i] = 'teal'  # Weak bullish
            else:
                if not pd.isna(fi_change.iloc[i]) and fi_change.iloc[i] < 0:
                    fi_color.iloc[i] = 'maroon'  # Strong bearish
                else:
                    fi_color.iloc[i] = 'orange'  # Weak bearish

        # Create results DataFrame
        results = pd.DataFrame({
            'basis': basis,
            'dev': dev,
            'upper_band': upper_band,
            'lower_band': lower_band,
            'upper_band_inner': upper_band_inner,
            'lower_band_inner': lower_band_inner,
            'force_index': fi_ema,
            'normalized_price': normprice,
            'histogram': hist,
            'fi_color': fi_color,
            'vw': vw
        }, index=df.index)

        return results

    def get_signals(self, df):
        """
        Generate trading signals based on the indicator

        Returns:
            DataFrame with signal information
        """
        results = self.calculate(df)

        signals = pd.DataFrame(index=df.index)

        # Force Index crosses zero
        signals['fi_cross_above_zero'] = (results['force_index'] > 0) & (results['force_index'].shift(1) <= 0)
        signals['fi_cross_below_zero'] = (results['force_index'] < 0) & (results['force_index'].shift(1) >= 0)

        # Normalized price crosses bands
        signals['price_above_upper'] = results['normalized_price'] > results['upper_band']
        signals['price_below_lower'] = results['normalized_price'] < results['lower_band']

        # Force index momentum
        signals['fi_strong_bullish'] = results['fi_color'] == 'lime'
        signals['fi_weak_bullish'] = results['fi_color'] == 'teal'
        signals['fi_strong_bearish'] = results['fi_color'] == 'maroon'
        signals['fi_weak_bearish'] = results['fi_color'] == 'orange'

        # Combined signals
        signals['buy_signal'] = signals['fi_cross_above_zero'] & (results['normalized_price'] > 0)
        signals['sell_signal'] = signals['fi_cross_below_zero'] & (results['normalized_price'] < 0)

        return signals, results


def scan_with_efi(ticker_symbol, results_dir, indicator_params=None):
    """
    Scan a single ticker using EFI indicator

    Args:
        ticker_symbol: Stock ticker
        results_dir: Directory containing CSV files
        indicator_params: Optional dict of indicator parameters

    Returns:
        Dict with signal information or None
    """
    try:
        csv_file = os.path.join(results_dir, f"{ticker_symbol}.csv")

        if not os.path.exists(csv_file):
            return None

        # Read CSV
        with open(csv_file, 'r') as f:
            first_line = f.readline().strip()

        has_header = 'Ticker' in first_line or 'Date' in first_line or 'Open' in first_line

        if has_header:
            df = pd.read_csv(csv_file, header=0, index_col=0)
        else:
            df = pd.read_csv(csv_file, header=None, index_col=0)
            df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']

        df.index = pd.to_datetime(df.index, errors='coerce')
        df = df[df.index.notna()]

        if len(df) < 100:  # Need enough data
            return None

        # Initialize indicator
        if indicator_params is None:
            indicator = EFI_Indicator()
        else:
            indicator = EFI_Indicator(**indicator_params)

        # Get signals
        signals, results = indicator.get_signals(df)

        # Check most recent signals
        latest_idx = -1
        current_date = df.index[latest_idx]
        current_price = df['Close'].iloc[latest_idx]

        # Check for recent signals (last 5 bars)
        recent_buy = signals['buy_signal'].iloc[-5:].any()
        recent_sell = signals['sell_signal'].iloc[-5:].any()

        if recent_buy or recent_sell:
            signal_type = 'BUY' if recent_buy else 'SELL'
            fi_value = results['force_index'].iloc[latest_idx]
            norm_price = results['normalized_price'].iloc[latest_idx]
            fi_color = results['fi_color'].iloc[latest_idx]

            return {
                'ticker': ticker_symbol,
                'date': current_date,
                'price': current_price,
                'signal': signal_type,
                'force_index': fi_value,
                'normalized_price': norm_price,
                'fi_color': fi_color,
                'upper_band': results['upper_band'].iloc[latest_idx],
                'lower_band': results['lower_band'].iloc[latest_idx]
            }

        return None

    except Exception as e:
        print(f"Error scanning {ticker_symbol}: {e}")
        return None


if __name__ == "__main__":
    """
    Example usage - you can import this class into other scanners
    """
    print("EFI Indicator Module")
    print("=" * 80)
    print()
    print("This module provides the EFI (Elder Force Index) indicator")
    print("with faux volume calculation using ATR.")
    print()
    print("To use in your scanners:")
    print("  from EFI_Indicator import EFI_Indicator, scan_with_efi")
    print()
    print("Example:")
    print("  indicator = EFI_Indicator()")
    print("  results = indicator.calculate(df)")
    print("  signals, indicator_data = indicator.get_signals(df)")
