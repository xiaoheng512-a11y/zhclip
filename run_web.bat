@echo off
REM zhclip Web 界面启动脚本
setlocal
set PATH=%PATH%;C:\tools\bin
set ZHCLIP_DATA=E:\Programs\zhclip\data
cd /d "%~dp0"
.venv\Scripts\python -m web.app
pause
