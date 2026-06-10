@echo off
REM ============================================================
REM  Ground Control Station Launcher (Python 3.13 - Miniconda3)
REM ============================================================
set PYTHON_EXE=C:\Users\Q\miniconda3\python.exe
set GCS_DIR=%~dp0

echo ============================================
echo   INAV Ground Control Station
echo   Python: %PYTHON_EXE%
%PYTHON_EXE% --version
echo ============================================
echo.

"%PYTHON_EXE%" "%GCS_DIR%main.py" %*

if %ERRORLEVEL% neq (
    echo.
    echo [ERROR] GCS exited with code %ERRORLEVEL%
    pause
)
