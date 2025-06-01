@echo off
cd /d "C:\Users\Dell Latitude 7400\Documents\GitHub\SimpleTrader"

call venv\Scripts\activate
echo Virtual environment activated.

:loop
python refactored.py
timeout /t 20 /nobreak
goto loop
