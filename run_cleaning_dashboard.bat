@echo off
setlocal
title CMS Data Cleaning Utility

cd /d "%~dp0"

REM Ensure venv exists
if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat
pip install -r requirements.txt >nul 2>&1

echo Launching CMS Data Cleaning Dashboard on port 8502...
streamlit run charge_point_cleaning\data_cleaning_dashboard.py --server.port 8502

pause
