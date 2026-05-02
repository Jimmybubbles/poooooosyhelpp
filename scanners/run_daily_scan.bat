@echo off
REM =====================================================
REM DAILY AUTO SCANNER - Windows Batch File
REM =====================================================
REM Schedule this in Windows Task Scheduler to run daily
REM Recommended time: After market close (5 PM ET / 8 AM AEST)
REM =====================================================

cd /d "c:\Users\James\poosy\poooooosyhelpp-1\watchlist_Scanner"
python daily_auto_scan.py

REM Keep window open if run manually (remove for scheduled tasks)
REM pause
