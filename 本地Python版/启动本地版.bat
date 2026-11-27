@echo off
chcp 65001 >nul
rem 咕咚校园 本地版 —— 备选启动方式（会保留一个命令行窗口）
cd /d %~dp0
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start pythonw drink_local.py
) else (
    start python drink_local.py
)
