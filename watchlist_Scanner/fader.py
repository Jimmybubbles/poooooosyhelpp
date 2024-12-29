import pandas as pd
import os
import numpy as np
from ta.trend import WMAIndicator
from stock_indicators import indicators
import logging

def jma(data, length, phase, power, source):
    """
    Jurik Moving Average (JMA)
    """
    phaseRatio = phase if -100 <= phase <= 100 else (100 if phase > 100 else -100)
    phaseRatio = (phaseRatio / 100) + 1.5
    beta = 0.45 * (length - 1) / (0.45 * (length - 1) + 2)
    alpha = np.power(beta, power)
    
    e0 = np.zeros_like(source)
    e1 = np.zeros_like(source)
    e2 = np.zeros_like(source)
    jma = np.zeros_like(source)
    
    for i in range(1, len(source)):
        e0[i] = (1 - alpha) * source[i] + alpha * e0[i-1]
        e1[i] = (source[i] - e0[i]) * (1 - beta) + beta * e1[i-1]
        e2[i] = (e0[i] + phaseRatio * e1[i] - jma[i-1]) * np.power(1 - alpha, 2) + np.power(alpha, 2) * e2[i-1]
        jma[i] = e2[i] + jma[i-1]
    
    return jma

def calculate_signal(df, fmal_zl, smal_zl, length_jma, phase, power, highlight_movements=True):
    """
    Calculate the Fader signal based on the given parameters
    """
    tmal_zl = fmal_zl + smal_zl
    Fmal_zl = smal_zl + tmal_zl
    Ftmal_zl = tmal_zl + Fmal_zl
    Smal_zl = Fmal_zl + Ftmal_zl

    # Adjust for the price column name in your data
    m1_zl = WMAIndicator(df['Close'], window=fmal_zl).wma()
    m2_zl = WMAIndicator(m1_zl, window=smal_zl).wma()
    m3_zl = WMAIndicator(m2_zl, window=tmal_zl).wma()
    m4_zl = WMAIndicator(m3_zl, window=Fmal_zl).wma()
    m5_zl = WMAIndicator(m4_zl, window=Ftmal_zl).wma()
    mavw_zl = indicators.get_hma(m5_zl, window=Smal_zl)

    jma_result = jma(df['Close'], length_jma, phase, power, df['Close'])

    signal = (mavw_zl + jma_result) / 2
    signal_color = np.where(signal > signal.shift(1), 'green', 'red') if highlight_movements else '#6d1e7f'
    
    return signal, signal_color

def process_csv_files(directory, output_directory, params):
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    for filename in os.listdir(directory):
        if filename.endswith(".csv"):
            file_path = os.path.join(directory, filename)
            df = pd.read_csv(file_path, parse_dates=[0], index_col=0)
            
            # Calculating signal
            df['Signal'], df['SignalColor'] = calculate_signal(df, **params)
            
            # Save updated data to new CSV
            output_file_path = os.path.join(output_directory, filename)
            df.to_csv(output_file_path)

            print(f"Processed and saved: {filename}")

# Parameters for calculation
params = {
    'fmal_zl': 1,
    'smal_zl': 1,
    'length_jma': 7,
    'phase': 126,
    'power': 0.89144,
    'highlight_movements': True
}

# Directory where your CSV files are stored
csv_directory = r'Squeezescan\CSV\updatedResults'
# Directory where you want to save the updated files
output_directory = r'Squeezescan/CSV/updatedFaderResults'

process_csv_files(csv_directory, output_directory, params)