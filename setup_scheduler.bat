@echo off
echo ============================================
echo  世界杯赔率自动抓取 - 定时任务配置
echo ============================================
echo.

:: 创建每2小时运行一次的任务
schtasks /create /tn "WorldCupOddsFetch" ^
  /tr "python C:\Users\shish\github-repos\worldcup-2026\fetch_odds.py" ^
  /sc hourly /mo 2 ^
  /st 00:00 ^
  /f

echo.
echo ✅ 定时任务已创建: WorldCupOddsFetch
echo    频率: 每2小时
echo    脚本: fetch_odds.py
echo.
echo 查看任务: schtasks /query /tn WorldCupOddsFetch
echo 删除任务: schtasks /delete /tn WorldCupOddsFetch /f
echo 手动运行: schtasks /run /tn WorldCupOddsFetch
echo.
pause
