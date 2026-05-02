"""
DAILY AUTO SCANNER
==================
Runs automatically via Windows Task Scheduler to:
1. Update daily stock data
2. Run all scanners
3. Save results with timestamps

Schedule this to run after market close (e.g., 5:00 PM ET / 8:00 AM AEST next day)
"""

import os
import sys
import subprocess
from datetime import datetime
import time

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
buylist_dir = os.path.join(script_dir, 'buylist')

# Ensure buylist directory exists
os.makedirs(buylist_dir, exist_ok=True)

# Create dated log file for each run
today = datetime.now().strftime('%Y-%m-%d')
log_file = os.path.join(buylist_dir, f'daily_scan_{today}.txt')

def log(message):
    """Log message to file and console"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{timestamp}] {message}"
    print(log_msg)

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(log_msg + '\n')

def run_script(script_name, description):
    """Run a Python script and return success/failure"""
    script_path = os.path.join(script_dir, script_name)

    if not os.path.exists(script_path):
        log(f"  SKIP: {script_name} not found")
        return False

    log(f"  Running: {description}...")

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=script_dir,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )

        if result.returncode == 0:
            log(f"  SUCCESS: {description}")
            return True
        else:
            log(f"  FAILED: {description}")
            if result.stderr:
                log(f"    Error: {result.stderr[:200]}")
            return False

    except subprocess.TimeoutExpired:
        log(f"  TIMEOUT: {description} took too long")
        return False
    except Exception as e:
        log(f"  ERROR: {description} - {str(e)}")
        return False

def main():
    """Main automation routine"""
    log("=" * 60)
    log("DAILY AUTO SCAN STARTED")
    log("=" * 60)

    start_time = time.time()
    results = {}

    # Step 1: Update daily data (append new rows)
    log("")
    log("STEP 1: UPDATING DAILY DATA")
    log("-" * 40)

    # Use AppendDailyData.py to add new rows to existing data
    data_updated = run_script('AppendDailyData.py', 'Append daily data to CSV files')

    if not data_updated:
        log("  Data update skipped or failed - continuing with existing data")

    # Step 2: Run scanners
    log("")
    log("STEP 2: RUNNING SCANNERS")
    log("-" * 40)

    scanners = [
        ('ultimate_scanner/UltimateScanner.py', 'Ultimate Scanner'),
        ('RangeLevelScanner.py', 'Range Level Scanner (25%/75% setups)'),
        ('RangeScoreScanner.py', 'Range+Score Scanner (daily report + email)'),
    ]

    for script, desc in scanners:
        results[script] = run_script(script, desc)

    # Step 3: Summary
    log("")
    log("=" * 60)
    log("SCAN COMPLETE - SUMMARY")
    log("=" * 60)

    elapsed = time.time() - start_time
    log(f"Total time: {elapsed/60:.1f} minutes")
    log("")

    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    log(f"Scanners run: {success_count}/{total_count} successful")

    for script, success in results.items():
        status = "OK" if success else "FAILED"
        log(f"  [{status}] {script}")

    log("")
    log(f"Results saved to: {buylist_dir}")
    log("=" * 60)

    # Create a "last run" marker file
    marker_file = os.path.join(buylist_dir, 'last_auto_scan.txt')
    with open(marker_file, 'w') as f:
        f.write(f"Last auto scan: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Scanners: {success_count}/{total_count} successful\n")

if __name__ == "__main__":
    main()
