# 2026世界杯赛程日历 - 一键安装脚本 (Windows)
# 启动本地HTTP服务器，浏览器打开赛程页面

Write-Host "🏆 2026 世界杯赛程日历 - 安装中..." -ForegroundColor Cyan

$port = 2026
$url = "http://localhost:$port"

# Check if python is available
$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    Write-Host "✅ 使用 Python 启动服务器..." -ForegroundColor Green
    Write-Host "🌐 浏览器将自动打开: $url" -ForegroundColor Yellow
    Start-Process $url
    python -m http.server $port
    exit 0
}

# Fallback to npx serve
$npx = Get-Command npx -ErrorAction SilentlyContinue
if ($npx) {
    Write-Host "✅ 使用 npx serve 启动服务器..." -ForegroundColor Green
    Write-Host "🌐 浏览器将自动打开: $url" -ForegroundColor Yellow
    Start-Process $url
    npx serve . -p $port
    exit 0
}

# Last resort: just open the HTML file
Write-Host "⚠️ 未检测到 Python 或 Node.js，直接打开 HTML 文件" -ForegroundColor Yellow
Start-Process "index.html"
Write-Host "✅ 已在浏览器中打开" -ForegroundColor Green
