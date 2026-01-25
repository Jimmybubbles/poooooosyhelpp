import pandas as pd
import numpy as np
from scipy import stats

class ROCWMA_Indicator:
    """
    ROC-Weighted MA Oscillator

    Combines Rate of Change (ROC) with weighted moving averages to create
    a momentum oscillator that identifies trend strength and reversals.

    Original: SeerQuant TradingView indicator
    Translation: Python
    """

    def __init__(self, roc_length=55, ma_length=7, signal_length=9,
                 neutral_threshold=0.5, ma_type='TEMA'):
        """
        Initialize ROCWMA Indicator

        Args:
            roc_length: Length for ROC calculation (default 55)
            ma_length: Length for moving average (default 7)
            signal_length: Length for signal line (default 9)
            neutral_threshold: Threshold for neutral zone (default 0.5)
            ma_type: Type of MA ('SMA', 'EMA', 'SMMA', 'WMA', 'VWMA', 'TEMA', 'DEMA', 'LSMA', 'HMA', 'ALMA')
        """
        self.roc_length = roc_length
        self.ma_length = ma_length
        self.signal_length = signal_length
        self.neutral_threshold = neutral_threshold
        self.ma_type = ma_type

    def calculate_ma(self, series, length, ma_type):
        """Calculate various types of moving averages"""

        if ma_type == 'SMA':
            return series.rolling(window=length).mean()

        elif ma_type == 'EMA':
            return series.ewm(span=length, adjust=False).mean()

        elif ma_type == 'SMMA':  # Smoothed MA (RMA in Pine)
            return series.ewm(alpha=1/length, adjust=False).mean()

        elif ma_type == 'WMA':
            weights = np.arange(1, length + 1)
            return series.rolling(window=length).apply(
                lambda x: np.dot(x, weights) / weights.sum(), raw=True
            )

        elif ma_type == 'VWMA':
            # Volume-weighted MA - requires volume data
            # For now, return EMA as fallback
            return series.ewm(span=length, adjust=False).mean()

        elif ma_type == 'TEMA':  # Triple EMA
            ema1 = series.ewm(span=length, adjust=False).mean()
            ema2 = ema1.ewm(span=length, adjust=False).mean()
            ema3 = ema2.ewm(span=length, adjust=False).mean()
            return 3 * (ema1 - ema2) + ema3

        elif ma_type == 'DEMA':  # Double EMA
            ema1 = series.ewm(span=length, adjust=False).mean()
            ema2 = ema1.ewm(span=length, adjust=False).mean()
            return 2 * ema1 - ema2

        elif ma_type == 'LSMA':  # Least Squares MA (Linear Regression)
            def linreg(y):
                if len(y) < length:
                    return np.nan
                x = np.arange(len(y))
                slope, intercept = np.polyfit(x, y, 1)
                return intercept + slope * (len(y) - 1)

            return series.rolling(window=length).apply(linreg, raw=True)

        elif ma_type == 'HMA':  # Hull MA
            half_length = int(length / 2)
            sqrt_length = int(np.sqrt(length))

            wma_half = series.rolling(window=half_length).apply(
                lambda x: np.dot(x, np.arange(1, half_length + 1)) / np.arange(1, half_length + 1).sum(),
                raw=True
            )
            wma_full = series.rolling(window=length).apply(
                lambda x: np.dot(x, np.arange(1, length + 1)) / np.arange(1, length + 1).sum(),
                raw=True
            )
            raw_hma = 2 * wma_half - wma_full

            # Apply WMA to the result
            return raw_hma.rolling(window=sqrt_length).apply(
                lambda x: np.dot(x, np.arange(1, sqrt_length + 1)) / np.arange(1, sqrt_length + 1).sum(),
                raw=True
            )

        elif ma_type == 'ALMA':  # Arnaud Legoux MA
            # Simplified ALMA calculation
            offset = 0.85
            sigma = 6
            m = offset * (length - 1)
            s = length / sigma

            def alma_weights(size):
                weights = np.zeros(size)
                for i in range(size):
                    weights[i] = np.exp(-((i - m) ** 2) / (2 * s * s))
                return weights / weights.sum()

            weights = alma_weights(length)
            return series.rolling(window=length).apply(
                lambda x: np.dot(x, weights), raw=True
            )

        else:
            # Default to EMA
            return series.ewm(span=length, adjust=False).mean()

    def calculate_roc(self, series, length):
        """Calculate Rate of Change"""
        return ((series - series.shift(length)) / series.shift(length)) * 100

    def normalize(self, series, length):
        """Normalize series to 0-1 range over lookback period"""
        rolling_min = series.rolling(window=length).min()
        rolling_max = series.rolling(window=length).max()
        return (series - rolling_min) / (rolling_max - rolling_min)

    def zscore(self, series, length):
        """Calculate Z-Score"""
        rolling_mean = series.rolling(window=length).mean()
        rolling_std = series.rolling(window=length).std()
        return (series - rolling_mean) / rolling_std

    def calculate(self, df):
        """
        Calculate ROC-Weighted MA Oscillator

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with oscillator, signal, and trade signals
        """
        # Calculate source (HLCC4 = (High + Low + Close + Close) / 4)
        src = (df['High'] + df['Low'] + df['Close'] + df['Close']) / 4

        # Calculate ROC
        roc = self.calculate_roc(src, self.roc_length)

        # Normalize ROC to 0-1 range
        normalized_roc = self.normalize(roc, self.roc_length)

        # Calculate base MA
        base_ma = self.calculate_ma(src, self.ma_length, self.ma_type)

        # Calculate weighted difference
        weighted_diff = normalized_roc * (src - base_ma)

        # Calculate ROC-Weighted MA
        rwma = base_ma + weighted_diff

        # Calculate oscillator (Z-Score)
        oscillator = self.zscore(rwma, self.roc_length)

        # Calculate signal line
        signal = oscillator.ewm(span=self.signal_length, adjust=False).mean()

        # Determine color/state
        color_state = pd.Series(index=df.index, dtype=object)

        for i in range(len(oscillator)):
            if pd.isna(oscillator.iloc[i]):
                color_state.iloc[i] = 'neutral'
                continue

            osc_val = oscillator.iloc[i]

            # Check if in neutral zone
            in_neutral = -self.neutral_threshold < osc_val < self.neutral_threshold

            if in_neutral:
                # Keep previous color
                if i > 0:
                    color_state.iloc[i] = color_state.iloc[i-1]
                else:
                    color_state.iloc[i] = 'neutral'
            else:
                # Determine color based on threshold
                if osc_val > self.neutral_threshold:
                    color_state.iloc[i] = 'bull'
                elif osc_val < -self.neutral_threshold:
                    color_state.iloc[i] = 'bear'
                else:
                    color_state.iloc[i] = 'neutral'

        # Detect signals (color changes)
        long_signal = pd.Series(False, index=df.index)
        short_signal = pd.Series(False, index=df.index)

        for i in range(1, len(color_state)):
            prev_color = color_state.iloc[i-1]
            curr_color = color_state.iloc[i]

            # Long signal: bear -> bull
            if curr_color == 'bull' and prev_color == 'bear':
                long_signal.iloc[i] = True

            # Short signal: bull -> bear
            if curr_color == 'bear' and prev_color == 'bull':
                short_signal.iloc[i] = True

        # Create result DataFrame
        result = pd.DataFrame({
            'oscillator': oscillator,
            'signal': signal,
            'color_state': color_state,
            'long_signal': long_signal,
            'short_signal': short_signal,
            'roc': roc,
            'normalized_roc': normalized_roc,
            'rwma': rwma
        })

        return result

    def get_current_state(self, df):
        """
        Get current state of the indicator

        Returns:
            Dictionary with current values and signals
        """
        result = self.calculate(df)

        if len(result) == 0:
            return None

        latest = result.iloc[-1]

        return {
            'oscillator': latest['oscillator'],
            'signal': latest['signal'],
            'color_state': latest['color_state'],
            'long_signal': latest['long_signal'],
            'short_signal': latest['short_signal'],
            'trend': 'Bullish' if latest['color_state'] == 'bull' else 'Bearish' if latest['color_state'] == 'bear' else 'Neutral',
            'strength': abs(latest['oscillator']) if not pd.isna(latest['oscillator']) else 0
        }


# Example usage and scanner integration
def scan_rocwma_signals(ticker_symbol, results_dir, roc_length=55, ma_length=7,
                        signal_length=9, neutral_threshold=0.5, ma_type='TEMA'):
    """
    Scan for ROCWMA signals on a ticker

    Returns:
        Dictionary with signal information or None
    """
    import os

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

        df.index = pd.to_datetime(df.index, errors='coerce', utc=True)
        df = df[df.index.notna()]

        # Need enough data
        if len(df) < max(roc_length, ma_length, signal_length) + 20:
            return None

        # Calculate indicator
        indicator = ROCWMA_Indicator(
            roc_length=roc_length,
            ma_length=ma_length,
            signal_length=signal_length,
            neutral_threshold=neutral_threshold,
            ma_type=ma_type
        )

        state = indicator.get_current_state(df)

        if state is None:
            return None

        # Get current price
        current_price = df['Close'].iloc[-1]
        current_date = df.index[-1]

        return {
            'ticker': ticker_symbol,
            'date': current_date,
            'price': current_price,
            'oscillator': state['oscillator'],
            'signal': state['signal'],
            'color_state': state['color_state'],
            'trend': state['trend'],
            'strength': state['strength'],
            'long_signal': state['long_signal'],
            'short_signal': state['short_signal']
        }

    except Exception as e:
        print(f"Error scanning {ticker_symbol}: {e}")
        return None


if __name__ == "__main__":
    # Example: Test the indicator
    print("ROCWMA Indicator - Python Translation")
    print("=" * 60)
    print()
    print("Available MA Types:")
    print("  - SMA:  Simple Moving Average")
    print("  - EMA:  Exponential Moving Average")
    print("  - SMMA: Smoothed Moving Average")
    print("  - WMA:  Weighted Moving Average")
    print("  - TEMA: Triple Exponential Moving Average (default)")
    print("  - DEMA: Double Exponential Moving Average")
    print("  - LSMA: Least Squares Moving Average")
    print("  - HMA:  Hull Moving Average")
    print("  - ALMA: Arnaud Legoux Moving Average")
    print()
    print("Signals:")
    print("  - Long (L):  Oscillator crosses above neutral threshold")
    print("  - Short (S): Oscillator crosses below neutral threshold")
    print()
    print("Usage:")
    print("  indicator = ROCWMA_Indicator()")
    print("  result = indicator.calculate(df)")
    print("  state = indicator.get_current_state(df)")
