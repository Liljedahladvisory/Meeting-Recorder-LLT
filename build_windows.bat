@echo off
REM ============================================================
REM  Meeting Recorder LLT — Windows Build Script
REM  Kör detta på en Windows-maskin för att bygga .exe + installer
REM ============================================================

echo.
echo  Meeting Recorder LLT — Windows Build
echo ========================================

REM 1. Kontrollera Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [FEL] Python hittades inte. Installera Python 3.11+ fran python.org
    pause
    exit /b 1
)

REM 2. Skapa virtuell miljö om den inte finns
if not exist "venv\" (
    echo  Skapar virtuell miljö...
    python -m venv venv
)

REM 3. Aktivera och installera beroenden
call venv\Scripts\activate.bat

echo  Installerar beroenden...
pip install -r requirements.txt --quiet
pip install pyinstaller --quiet

REM 4. Bygg .exe med PyInstaller
echo  Bygger .exe...
pyinstaller ^
  --windowed ^
  --name "Meeting Recorder LLT" ^
  --icon MeetingRecorder.ico ^
  --add-data "MeetingRecorder.ico;." ^
  --noconfirm ^
  meeting_recorder.py

if errorlevel 1 (
    echo [FEL] PyInstaller misslyckades.
    pause
    exit /b 1
)

echo.
echo  Klar! Appen finns i: dist\Meeting Recorder LLT\
echo  Kör Meeting Recorder LLT.exe for att testa.
echo.
pause
