@echo off
chcp 65001 >nul
title 원가구성 비교 분석 도구 - 설치 및 실행
cd /d "%~dp0"

echo ============================================
echo   원가구성 비교 분석 도구
echo ============================================
echo.

REM 1. Python 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo.
    echo Python 3.10 이상을 설치해 주세요:
    echo   https://www.python.org/downloads/
    echo 설치 시 "Add Python to PATH" 체크를 꼭 하세요.
    echo.
    pause
    exit /b 1
)

echo [1/3] Python 확인 완료
python --version
echo.

REM 2. 의존성 설치 (첫 실행만)
if not exist ".deps_installed" (
    echo [2/3] 의존성 설치 중... (최초 1~3분 소요)
    python -m pip install --upgrade pip >nul 2>&1
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [오류] 의존성 설치에 실패했습니다.
        pause
        exit /b 1
    )
    echo. > .deps_installed
    echo [2/3] 의존성 설치 완료
) else (
    echo [2/3] 의존성 이미 설치됨
)
echo.

REM 3. 앱 실행
echo [3/3] 앱 실행 중...
echo.
echo   브라우저가 자동으로 열립니다.
echo   http://localhost:8501
echo.
start "" http://localhost:8501
python -m streamlit run app.py --server.headless true --server.port 8501

pause
