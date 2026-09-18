@echo off
title 원가구성 비교 분석 도구
cd /d "%~dp0"
echo ============================================
echo   원가구성 비교 분석 도구
echo   http://localhost:8501
echo ============================================
echo.
python -m streamlit run app.py --server.headless true --server.port 8501
pause
