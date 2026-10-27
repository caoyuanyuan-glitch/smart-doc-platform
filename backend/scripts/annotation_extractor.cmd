@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0review_comment_extractor"

REM Old single-file launcher. Do not call powershell.exe; that flashes
REM console windows on some colleague PCs and they cannot be closed.

if not exist "%CD%\annotation_extractor.pyw" (
    echo Missing review_comment_extractor\annotation_extractor.pyw
    pause
    exit /b 1
)

if exist "%SystemRoot%\pyw.exe" (
    start "" "%SystemRoot%\pyw.exe" "%CD%\annotation_extractor.pyw"
    exit /b 0
)

for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
    if exist "%%~D\pythonw.exe" (
        start "" "%%~D\pythonw.exe" "%CD%\annotation_extractor.pyw"
        exit /b 0
    )
)

echo pythonw.exe was not found. Install Python 3 from python.org
echo Tick "Add python.exe to PATH", then: py -m pip install PyMuPDF
pause
exit /b 1
