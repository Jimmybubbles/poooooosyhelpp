import re
import os

# Input file path
input_file_path = r"poooooosyhelpp\watchlist_Scanner\buylist\scan_results_text.txt"
# Output file path for sorted data
output_file_path = r"poooooosyhelpp\watchlist_Scanner\buylist"

# Function to extract ticker and price
def extract_info(line):
    match = re.match(r'BUY (\w+) \d{2}/\d{2}/\d{4} : Upside Breakout (\d+(?:\.\d+)?)', line)
    if match:
        ticker, price = match.groups()
        return line, float(price)  # Return the whole line along with the price
    return None, None

# Read from file and collect ticker and price
tickers_and_prices = []
with open(input_file_path, 'r') as file:
    for line in file:
        line_data, price = extract_info(line.strip())
        if line_data and price:
            tickers_and_prices.append((line_data, price))

# Sort by price from lowest to highest
sorted_lines = sorted(tickers_and_prices, key=lambda x: x[1])

# Ensure the directory exists
output_dir = os.path.dirname(output_file_path)
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Write sorted data to a new file
try:
    with open(output_file_path, 'w') as file:
        for line, _ in sorted_lines:
            file.write(line + '\n')
    print(f"Sorted data has been written to {output_file_path}")
except PermissionError:
    print(f"Permission denied: Unable to write to {output_file_path}")
except IOError as e:
    print(f"An error occurred while writing to file: {e}")