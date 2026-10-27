@echo off
setlocal
cd /d "%~dp0review_comment_extractor"
call "%~dp0review_comment_extractor\打开审核意见汇总工具.cmd"
exit /b %errorlevel%
