@echo off
chcp 65001 >nul
echo ============================================
echo  世界杯赔率自动抓取 - 一键安装
echo ============================================
echo.

:: 1. 安装Python依赖
echo [1/3] 安装Python依赖...
pip install websockets -q
if %errorlevel% neq 0 (
    echo ❌ pip安装失败,请检查Python是否已安装
    pause
    exit /b 1
)
echo ✅ websockets 已安装
echo.

:: 2. 创建定时任务(每小时)
echo [2/3] 创建Windows定时任务(每小时)...
schtasks /create /tn "WorldCupOddsFetch" ^
  /tr "cmd /c \"set PYTHONIOENCODING=utf-8 && python %USERPROFILE%\github-repos\worldcup-2026\fetch_odds.py\"" ^
  /sc hourly /mo 1 ^
  /st 00:00 ^
  /f 2>nul

if %errorlevel% equ 0 (
    echo ✅ 定时任务已创建: 每小时自动抓取
) else (
    echo ⚠️ 定时任务可能已存在,尝试更新...
    schtasks /change /tn "WorldCupOddsFetch" ^
      /tr "cmd /c \"set PYTHONIOENCODING=utf-8 && python %USERPROFILE%\github-repos\worldcup-2026\fetch_odds.py\"" ^
      /sc hourly /mo 1 ^
      /f 2>nul
    echo ✅ 定时任务已更新
)
echo.

:: 3. 首次运行测试
echo [3/3] 首次运行测试...
echo.
echo   脚本会自动启动Chrome/Edge浏览器(无需手动打开)
echo   如果安全软件弹出警告请点"允许"
echo.
python "%USERPROFILE%\github-repos\worldcup-2026\fetch_odds.py" --dry-run

echo.
echo ============================================
echo  安装完成!
echo ============================================
echo.
echo   自动抓取: 每小时整点
echo   查看任务: schtasks /query /tn WorldCupOddsFetch
echo   删除任务: schtasks /delete /tn WorldCupOddsFetch /f
echo   手动运行: python fetch_odds.py
echo.
echo   浏览器会自动启动,不需要手动打开!
echo ============================================
pause
