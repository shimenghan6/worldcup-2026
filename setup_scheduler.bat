@echo off
:: 自动请求管理员权限
net session >nul 2>&1
if errorlevel 1 (
    echo 正在请求管理员权限...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo ============================================
echo  世界杯赔率自动抓取 - 一键安装(管理员)
echo ============================================
echo.

echo [1/3] 安装依赖...
pip install requests -q 2>nul
if errorlevel 1 (
    echo [FAIL] pip install requests 失败
    pause & exit /b 1
)
echo [OK] requests 已安装
echo.

echo [2/3] 创建定时任务...
:: 删旧任务
schtasks /delete /tn WorldCupOddsFetch /f 2>nul
schtasks /delete /tn WorldCupOddsFetch_Boot /f 2>nul
schtasks /delete /tn WorldCupOddsFetch_Hourly /f 2>nul

:: 开机自启
schtasks /create /tn WorldCupOddsFetch_Boot /tr "%USERPROFILE%\github-repos\worldcup-2026\run_fetch.bat" /sc onstart /rl HIGHEST /f
if errorlevel 1 (echo [WARN] 开机自启创建失败) else (echo [OK] 开机自启: 每次开机自动跑)

:: 每小时
schtasks /create /tn WorldCupOddsFetch_Hourly /tr "%USERPROFILE%\github-repos\worldcup-2026\run_fetch.bat" /sc hourly /mo 1 /st 00:00 /rl HIGHEST /f
if errorlevel 1 (echo [WARN] 每小时创建失败) else (echo [OK] 每小时: 自动抓取赔率)
echo.

echo [3/3] 试跑一次...
python "%USERPROFILE%\github-repos\worldcup-2026\fetch_odds.py" --dry-run
echo.

echo ============================================
echo  安装完成!
echo ============================================
echo   开机自启: WorldCupOddsFetch_Boot
echo   每小时:   WorldCupOddsFetch_Hourly
echo.
echo   关机开机 → 开机自动跑
echo   睡眠唤醒 → 下一个整点自动补跑
echo.
echo   手动运行: python fetch_odds.py
echo   删除任务: 运行一次就会看到上面报错,再运行一次
echo ============================================
pause
