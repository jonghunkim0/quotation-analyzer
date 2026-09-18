@echo off
chcp 65001 >nul
title 원가구성 비교 분석 도구 - 배포 패키지 생성
cd /d "%~dp0"

echo ============================================
echo   배포 패키지 생성
echo ============================================
echo.

python make_package.py

echo.
pause
