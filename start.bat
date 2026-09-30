@echo off
chcp 65001 >nul 2>&1
title 웹툰 메이커

echo ============================================
echo   웹툰 메이커 - 시작 중...
echo ============================================
echo.

:: 가상환경 확인/생성
if not exist ".venv" (
    echo [1/3] 가상환경 생성 중...
    python -m venv .venv
    if errorlevel 1 (
        echo [오류] Python 3.11 이상이 필요합니다.
        pause
        exit /b 1
    )
)

:: 가상환경 활성화
call .venv\Scripts\activate.bat

:: 의존성 설치
echo [2/3] 의존성 확인 중...
pip install -r requirements.txt -q

:: 서버 시작 + 브라우저 자동 오픈
echo [3/3] 서버 시작 중...
echo.
echo   브라우저에서 http://localhost:8000 으로 접속하세요.
echo   종료하려면 이 창을 닫거나 Ctrl+C를 누르세요.
echo.

start "" http://localhost:8000
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
