@echo off
cd /d "%~dp0"
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

powershell -NoProfile -Command "$client = New-Object Net.Sockets.TcpClient; try { $client.Connect('127.0.0.1', 54321); Start-Process 'http://127.0.0.1:54321/'; exit 0 } catch { exit 1 } finally { $client.Dispose() }"
if %errorlevel% equ 0 exit /b 0

py studio_server.py
pause
