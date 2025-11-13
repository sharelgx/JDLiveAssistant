@echo off
chcp 65001 >nul
echo ============================================================
echo 京东直播后台页面诊断工具
echo ============================================================
echo.

cd /d "%~dp0"
cd ..

if not exist "venv\Scripts\python.exe" (
    echo 错误: 未找到虚拟环境，请先创建虚拟环境
    echo 或者直接使用系统 Python: python scripts\diagnose_page.py
    pause
    exit /b 1
)

echo 正在启动诊断程序...
echo.
venv\Scripts\python.exe scripts\diagnose_page.py %*

echo.
echo ============================================================
pause

