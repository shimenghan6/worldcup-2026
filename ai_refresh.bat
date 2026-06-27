@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d C:\Users\shish\github-repos\worldcup-2026

:: Step 1: Run fetch_odds.py to update SPF + results + template dimensions
python fetch_odds.py

:: Step 2: Write trigger file as signal for Claude to run lottery-analyzer skill
echo %date% %time% AI refresh needed — trigger lottery-analyzer skill > .ai_refresh_trigger

:: Step 3: Log completion
echo %date% %time% ai_refresh.bat completed >> ai_refresh.log
