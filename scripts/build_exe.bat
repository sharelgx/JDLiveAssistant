@echo off
setlocal enabledelayedexpansion

REM =============================================================
REM  JD Live Assistant 打包脚本（基于 PyInstaller）
REM  使用方法：双击运行，等待执行完成
REM =============================================================

REM 项目根目录（脚本所在目录的上一级）
set ROOT=%~dp0..
pushd %ROOT%

echo [1/6] 创建虚拟环境 (venv)
if not exist venv (
    python -m venv venv
)

echo [2/6] 激活虚拟环境
call venv\Scripts\activate.bat

echo [3/6] 升级 pip 并安装依赖
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo [4/6] 安装 Playwright 浏览器依赖（若已安装将自动跳过）
python -m playwright install chromium

echo [5/6] 执行 PyInstaller 打包
set DIST_DIR=%ROOT%\dist
if exist %DIST_DIR% (
    rmdir /s /q %DIST_DIR%
)

set SPEC_OPTS=--clean --noconfirm --onefile --noconsole
set SPEC_OPTS=%SPEC_OPTS% --name JDLiveAssistant
set SPEC_OPTS=%SPEC_OPTS% --collect-submodules playwright --collect-data playwright
set SPEC_OPTS=%SPEC_OPTS% --add-data "%ROOT%\JD_Live_Assistant\config;JD_Live_Assistant\config"

pyinstaller %SPEC_OPTS% JD_Live_Assistant\main.py

echo [6/6] 打包完成
echo ---------------------------------------------
echo  输出文件位于: %ROOT%\dist\JDLiveAssistant.exe
echo  初次运行若防毒軟件提示，請選擇允許。
echo ---------------------------------------------

popd

