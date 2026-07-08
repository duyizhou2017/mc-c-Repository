@echo off
:: 设置编码为UTF-8，防止中文乱码
chcp 65001 >nul
title Minecraft Python 游戏环境一键配置工具
cls

echo ======================================================
echo       Minecraft Python 3.1 游戏环境一键配置工具
echo ======================================================
echo.

:: 1. 检查 Python 是否已安装
echo 正在检查本地 Python 环境...
python --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [成功] 检测到本地已安装 Python！
    goto :INSTALL_LIBS
) else (
    echo [提示] 检测到本地未安装 Python，准备启动自动下载安装...
    goto :DOWNLOAD_PYTHON
)

:DOWNLOAD_PYTHON
echo.
echo ------------------------------------------------------
echo 正在从华为云镜像源快速下载 Python 3.10 安装包...
echo (请保持网络畅通，这可能需要一分钟左右)
echo ------------------------------------------------------
:: 使用 PowerShell 下载官方稳定版 Python
powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://mirrors.huaweicloud.com/python/3.10.11/python-3.10.11-amd64.exe' -OutFile '%TEMP%\python_installer.exe'"

if not exist "%TEMP%\python_installer.exe" (
    echo [错误] Python 下载失败，请检查网络连接！
    pause
    exit
)

echo.
echo 正在进行自动静默安装并配置系统环境变量(PATH)...
echo 请在弹出的系统提示中允许运行...
:: PrependPath=1 表示自动自动添加环境变量，Include_pip=1 表示自带pip工具
start /wait "" "%TEMP%\python_installer.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1

:: 刷新当前CMD窗口的环境变量
set "PATH=%SystemRoot%\system32;%SystemRoot%;%SystemRoot%\System32\Wbem;%SYSTEMROOT%\System32\WindowsPowerShell\v1.0\"
for /f "tokens=2*" %%A in ('reg query "HKLM\System\CurrentControlSet\Control\Session Manager\Environment" /v Path') do set "PATH=%%B;%PATH%"

:: 再次验证安装结果
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [警告] 自动安装可能未完全成功。
    echo 请前往 Python 官网 (https://www.python.org) 手动下载安装，并务必勾选 "Add Python to PATH"。
    pause
    exit
)
echo [成功] Python 安装并配置成功！
goto :INSTALL_LIBS

:INSTALL_LIBS
echo.
echo ------------------------------------------------------
echo 正在配置 pip 国内加速镜像源并安装游戏依赖库...
echo ------------------------------------------------------
:: 切换清华大学清华源，防止下载超时报错
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple

echo.
echo [1/2] 正在安装 3D 游戏引擎: Ursina ...
python -m pip install ursina -i https://pypi.tuna.tsinghua.edu.cn/simple

echo.
echo [2/2] 正在安装无限地形算法: perlin-noise (柏林噪声) ...
python -m pip install perlin-noise -i https://pypi.tuna.tsinghua.edu.cn/simple

echo.
echo ======================================================
echo 检查环境完整性：
echo ------------------------------------------------------
python -c "import ursina; print('[OK] Ursina 引擎正常')" 2>nul
python -c "import perlin_noise; print('[OK] 柏林噪声算法正常')" 2>nul
echo ======================================================
echo.
echo 所有游戏依赖环境已配置完毕！现在您可以双击启动游戏脚本了。
echo.
pause
exit