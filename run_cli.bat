@echo off
REM zhclip CLI 启动脚本
setlocal
set PATH=%PATH%;C:\tools\bin
set ZHCLIP_DATA=E:\Programs\zhclip\data
cd /d "%~dp0"
.venv\Scripts\python -m zhclip.cli %*
pause
