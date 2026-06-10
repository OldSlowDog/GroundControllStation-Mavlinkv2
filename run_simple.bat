@echo off
:: Smart Python launcher - finds working Python automatically

set PYTHON_CMD=

:: Try common locations
if exist "C:\Python39\python.exe" set PYTHON_CMD=C:\Python39\python.exe
if exist "C:\Python310\python.exe" set PYTHON_CMD=C:\Python310\python.exe
if exist "C:\Python311\python.exe" set PYTHON_CMD=C:\Python311\python.exe
if exist "%LOCALAPPDATA%\Programs\Python\Python39\python.exe" set PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python39\python.exe

:: Try conda (test if it works)
if "%PYTHON_CMD%"=="" (
    if exist "C:\Users\Q\miniconda3\python.exe" (
        "C:\Users\Q\miniconda3\python.exe" --version >nul 2>&1
        if !errorlevel! equ 0 set PYTHON_CMD=C:\Users\Q\miniconda3\python.exe
    )
)

:: Launch with found Python
if not "%PYTHON_CMD%"=="" (
    echo Using: %PYTHON_CMD%
    "%PYTHON_CMD%" main.py
) else (
    echo No working Python found!
    echo Trying default python...
    python main.py
)

pause