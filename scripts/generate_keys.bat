@echo off
chcp 65001 >nul
echo ============================================================
echo 卡密生成工具
echo ============================================================
echo.

cd /d "%~dp0"
cd ..

if not exist "venv\Scripts\python.exe" (
    echo 错误: 未找到虚拟环境，请先创建虚拟环境
    echo 或者直接使用系统 Python: python scripts\generate_keys.py
    pause
    exit /b 1
)

venv\Scripts\python.exe scripts\generate_keys.py

pause

