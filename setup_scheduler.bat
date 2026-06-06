@echo off
echo ============================================
echo  世界杯赔率自动抓取 - 一键安装
echo ============================================
echo.

echo [1/2] 安装依赖...
pip install requests -q 2>nul
if errorlevel 1 (
    echo [FAIL] pip install requests 失败, 请检查Python
    pause & exit /b 1
)
echo [OK] requests 已安装
echo.

echo [2/2] 创建定时任务(每小时)...
schtasks /create /tn WorldCupOddsFetch /tr "C:\Users\shish\github-repos\worldcup-2026\run_fetch.bat" /sc hourly /mo 1 /st 00:00 /f 2>nul
if errorlevel 1 (
    echo [WARN] 创建失败, 尝试更新已有任务...
    schtasks /change /tn WorldCupOddsFetch /tr "C:\Users\shish\github-repos\worldcup-2026\run_fetch.bat" /sc hourly /mo 1 /f 2>nul
)
echo [OK] 定时任务就绪(每小时)
echo.

echo [测试] 试跑一次抓取...
python C:\Users\shish\github-repos\worldcup-2026\fetch_odds.py --dry-run
echo.

echo ============================================
echo  安装完成! 每小时自动抓取赔率
echo  手动运行: python fetch_odds.py
echo  删除任务: schtasks /delete /tn WorldCupOddsFetch /f
echo ============================================
pause
