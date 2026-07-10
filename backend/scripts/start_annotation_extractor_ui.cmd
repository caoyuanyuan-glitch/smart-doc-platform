@echo off
setlocal
cd /d "%~dp0"

where pyw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pyw.exe "%~dp0annotation_extractor_ui.pyw"
    exit /b 0
)

where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pythonw.exe "%~dp0annotation_extractor_ui.pyw"
    exit /b 0
)

where py.exe >nul 2>nul
if not errorlevel 1 (
    py.exe "%~dp0annotation_extractor_ui.py"
    exit /b %errorlevel%
)

where python.exe >nul 2>nul
if not errorlevel 1 (
    python.exe "%~dp0annotation_extractor_ui.py"
    exit /b %errorlevel%
)

echo Python was not found. Please install Python and try again.
pause
exit /b 1
