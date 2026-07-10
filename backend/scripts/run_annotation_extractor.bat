@echo off
setlocal
cd /d "%~dp0"

set "OUTPUT=%CD%\人工审核意见汇总.md"

py "%~dp0extract_pdf_annotations.py" "%CD%" "%OUTPUT%"
if not errorlevel 1 goto success

python "%~dp0extract_pdf_annotations.py" "%CD%" "%OUTPUT%"
if not errorlevel 1 goto success

echo Python was not found. Please install Python or add python/py to PATH.
goto error

:success
echo.
echo Output file: %OUTPUT%
timeout /t 3 /nobreak >nul
exit /b 0

:error
echo.
echo Failed. Keep this window open and send the error message to the maintainer.
pause
exit /b 1
