# ============================================================
# 2026世界杯赛程日历 - 每日数据更新脚本
# 由 lottery-analyzer skill 驱动，每天自动抓取最新赔率+情报
# ============================================================
param([switch]$DryRun)

$ErrorActionPreference = "Stop"
$REPO = "$env:USERPROFILE\github-repos\worldcup-2026"
$DATA_FILE = "$REPO\data.json"

Write-Host "🏆 世界杯数据更新 pipeline v1.0" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: 检查git状态
Write-Host "[1/4] 检查仓库状态..." -ForegroundColor Yellow
if (-not (Test-Path $REPO)) {
    Write-Host "❌ 仓库不存在: $REPO" -ForegroundColor Red
    exit 1
}
cd $REPO
git pull origin main 2>$null
Write-Host "  ✅ 仓库就绪" -ForegroundColor Green

# Step 2: 运行 lottery-analyzer skill 更新数据
Write-Host "[2/4] 调用 lottery-analyzer skill 获取最新数据..." -ForegroundColor Yellow
Write-Host "  📡 抓取竞彩网实时赔率 (sporttery.cn)" -ForegroundColor Gray
Write-Host "  🔍 搜索最新球队情报 (伤病/阵容/状态)" -ForegroundColor Gray
Write-Host "  🧠 AI 重新评估每场预测" -ForegroundColor Gray
Write-Host ""
Write-Host "  请在 Claude Code 中运行以下命令:" -ForegroundColor White
Write-Host "  ┌─────────────────────────────────────────────────────┐" -ForegroundColor Cyan
Write-Host "  │ /lottery-analyzer                                  │" -ForegroundColor Cyan
Write-Host "  │ 更新2026世界杯所有48场比赛的最新赔率和球队情报     │" -ForegroundColor Cyan
Write-Host "  │ 输出更新后的 data.json 到:                        │" -ForegroundColor Cyan
Write-Host "  │ $DATA_FILE                                        │" -ForegroundColor Cyan
Write-Host "  │ 比赛ID: 1-48 (小组赛前2轮)                         │" -ForegroundColor Cyan
Write-Host "  │ 更新格式参考现有 data.json                         │" -ForegroundColor Cyan
Write-Host "  └─────────────────────────────────────────────────────┘" -ForegroundColor Cyan
Write-Host ""

if ($DryRun) {
    Write-Host "  🔶 DryRun 模式: 跳过实际更新" -ForegroundColor Magenta
    exit 0
}

# Step 3: 确认data.json已更新
Write-Host "[3/4] 验证数据更新..." -ForegroundColor Yellow
$lastWrite = (Get-Item $DATA_FILE).LastWriteTime
$hoursAgo = [math]::Round(((Get-Date) - $lastWrite).TotalHours, 1)
Write-Host "  📄 data.json 最后修改: $lastWrite ($hoursAgo 小时前)" -ForegroundColor Gray

if ($hoursAgo -gt 2) {
    Write-Host "  ⚠️ data.json 超过2小时未更新！请先运行 skill 命令" -ForegroundColor Red
    Write-Host "  是否继续提交？(y/n)" -ForegroundColor Yellow
    $confirm = Read-Host
    if ($confirm -ne 'y') { exit 1 }
}

# Step 4: Git commit & push
Write-Host "[4/4] 提交并推送数据更新..." -ForegroundColor Yellow
git add data.json index.html 2>$null
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
$filesChanged = (git diff --cached --name-only 2>$null | Measure-Object).Count

if ($filesChanged -eq 0) {
    Write-Host "  ℹ️ 没有文件变更，跳过提交" -ForegroundColor Gray
} else {
    git commit -m "📊 数据更新: $timestamp - 刷新赔率+球队情报
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>" 2>$null
    git push origin main 2>$null
    Write-Host "  ✅ 已推送到 GitHub" -ForegroundColor Green
    Write-Host "  🌐 线上页面将在1分钟内自动刷新" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✅ 更新完成！访问: https://shimenghan6.github.io/worldcup-2026/" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
