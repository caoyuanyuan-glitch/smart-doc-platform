@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Review Comment Extractor
echo Starting review comment extractor...
echo.

REM Fallback launcher when VBS is blocked. Do not call powershell.exe.

if not exist "%~dp0annotation_extractor.pyw" (
    echo Missing annotation_extractor.pyw
    echo Keep this cmd file in the same folder as annotation_extractor.pyw.
    pause
    exit /b 1
)

set "PYW="

for %%V in (3.14 3.13 3.12 3.11 3.10 3.9 3.8) do (
    for %%K in (
        "HKCU\Software\Python\PythonCore\%%V\InstallPath"
        "HKLM\Software\Python\PythonCore\%%V\InstallPath"
        "HKLM\Software\Wow6432Node\Python\PythonCore\%%V\InstallPath"
    ) do (
        for /f "tokens=2*" %%A in ('reg query %%K /ve 2^>nul ^| findstr /I "REG_SZ"') do (
            set "DIR=%%B"
            if not "!DIR!"=="" (
                if not "!DIR:~-1!"=="\" set "DIR=!DIR!\"
                if exist "!DIR!pythonw.exe" set "PYW=!DIR!pythonw.exe"
            )
        )
    )
)

if not defined PYW (
    for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
        if exist "%%~D\pythonw.exe" set "PYW=%%~D\pythonw.exe"
    )
)

if not defined PYW (
    for %%P in (
        "%UserProfile%\anaconda3\pythonw.exe"
        "%UserProfile%\miniconda3\pythonw.exe"
        "%UserProfile%\AppData\Local\anaconda3\pythonw.exe"
        "C:\Python312\pythonw.exe"
        "C:\Python311\pythonw.exe"
    ) do (
        if exist %%P set "PYW=%%~P"
    )
)

if not defined PYW (
    for /f "delims=" %%P in ('where pythonw.exe 2^>nul') do (
        echo %%P | find /I "WindowsApps" >nul
        if errorlevel 1 if exist "%%P" set "PYW=%%P"
    )
)

if not defined PYW (
    if exist "%SystemRoot%\pyw.exe" set "PYW=%SystemRoot%\pyw.exe"
)

if not defined PYW (
    echo pythonw.exe was not found.
    echo Install Python 3 from https://www.python.org/downloads/
    echo During setup, tick: Add python.exe to PATH
    echo Do not use the Microsoft Store Python stub.
    echo Then open cmd.exe and run:
    echo     py -m pip install PyMuPDF
    pause
    exit /b 1
)

echo Using: %PYW%
"%PYW%" -c "import tkinter"
if errorlevel 1 (
    echo.
    echo This Python cannot open a GUI. tkinter is missing or the launcher is broken.
    echo Path: %PYW%
    pause
    exit /b 1
)

start "" "%PYW%" "%~dp0annotation_extractor.pyw"
exit /b 0
