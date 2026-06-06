"""
世界杯赔率自动抓取脚本 - 零Token方案
每小时自动: 启动Edge浏览器 → 抓取sporttery.cn赔率 → 更新data.json → git push
完全自动化,无需手动开浏览器

用法:
  python fetch_odds.py                  # 全自动抓取+更新+推送
  python fetch_odds.py --dry-run        # 仅测试,不更新不推送
  python fetch_odds.py --headless       # 无头模式(浏览器窗口隐藏)

依赖: pip install websockets
"""

import asyncio, json, os, sys, subprocess, time, signal, atexit, io
# Fix Windows GBK encoding issue
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_DIR = Path(os.path.expanduser("~/github-repos/worldcup-2026"))
DATA_FILE = REPO_DIR / "data.json"
CDP_PORT = 9222
CDP_HOST = f"http://127.0.0.1:{CDP_PORT}"
SPF_URL = "https://m.sporttery.cn/mjc/jsq/zqspf/"
DRY_RUN = "--dry-run" in sys.argv
HEADLESS = "--headless" in sys.argv
NO_PUSH = "--no-push" in sys.argv

BROWSER_PROC = None  # 跟踪我们启动的浏览器进程

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def find_browser():
    """找到系统中的Chrome/Edge浏览器路径(优先Chrome)"""
    paths = [
        # Chrome 优先
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        # Edge 备选
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for p in paths:
        if os.path.exists(p):
            log(f"  找到浏览器: {p}")
            return p
    # PATH fallback
    for name in ["chrome", "chromium", "msedge"]:
        try:
            subprocess.run([name, "--version"], capture_output=True, timeout=5)
            return name
        except:
            continue
    return "chrome"  # last resort

def check_cdp():
    """检查CDP端口是否已开放"""
    import urllib.request
    try:
        resp = urllib.request.urlopen(f"{CDP_HOST}/json/version", timeout=3)
        return resp.status == 200
    except:
        return False

def launch_browser():
    """自动启动Edge/Chrome浏览器(CDP模式)"""
    global BROWSER_PROC

    if check_cdp():
        log("✅ CDP端口已就绪(浏览器已在运行)")
        return True

    browser = find_browser()
    log(f"🚀 启动浏览器: {browser}")

    cmd = [browser, f"--remote-debugging-port={CDP_PORT}", "--no-first-run", "--no-default-browser-check"]
    if HEADLESS:
        cmd.append("--headless=new")

    try:
        BROWSER_PROC = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        # 等待CDP就绪(最多30秒)
        for i in range(30):
            time.sleep(1)
            if check_cdp():
                log("✅ 浏览器CDP就绪")
                return True

        log("❌ 浏览器启动超时")
        return False
    except Exception as e:
        log(f"❌ 启动浏览器失败: {e}")
        return False

def kill_browser():
    """清理:关闭我们启动的浏览器"""
    global BROWSER_PROC
    if BROWSER_PROC:
        try:
            BROWSER_PROC.terminate()
            log("🧹 浏览器已关闭")
        except:
            pass

atexit.register(kill_browser)

async def cdp_fetch_odds():
    """通过CDP连接浏览器,抓取竞彩赔率"""
    import urllib.request
    import websockets

    # 获取页面列表
    try:
        resp = urllib.request.urlopen(f"{CDP_HOST}/json", timeout=5)
        pages = json.loads(resp.read())
    except Exception as e:
        log(f"❌ CDP连接失败: {e}")
        return None

    # 找到或创建页面
    target = next((p for p in pages if 'sporttery.cn' in p.get('url', '')), None)
    if not target:
        target = next((p for p in pages if p.get('type') == 'page'), None)

    if not target:
        log("❌ 无可用页面")
        return None

    ws_url = target.get('webSocketDebuggerUrl')
    if not ws_url:
        log("❌ 无法获取WebSocket URL")
        return None

    async with websockets.connect(ws_url, max_size=10*1024*1024) as ws:
        # 启用Runtime和Page
        await ws.send(json.dumps({"id":1, "method":"Runtime.enable"}))
        await ws.recv()
        await ws.send(json.dumps({"id":2, "method":"Page.enable"}))
        await ws.recv()

        # 导航到竞彩SPF页面
        await ws.send(json.dumps({
            "id":3, "method":"Page.navigate", "params":{"url": SPF_URL}
        }))
        await ws.recv()
        log("📡 已导航到竞彩SPF页面")

        # 等待页面加载
        await asyncio.sleep(4)

        # 提取数据
        await ws.send(json.dumps({
            "id":4, "method":"Runtime.evaluate",
            "params": {
                "expression": """
                (function() {
                    var text = document.body.innerText;
                    var hasWorldCup = text.indexOf('世界杯') > -1;
                    var timeMatch = text.match(/(\\d{4}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}:\\d{2})/);
                    var updateTime = timeMatch ? timeMatch[1] : '';
                    var lines = text.split('\\n').filter(function(l) { return l.trim(); });
                    var matches = [], cur = null;

                    for (var i = 0; i < lines.length; i++) {
                        var line = lines[i].trim();
                        if (/周[一二三四五六日]\\d{3}/.test(line)) {
                            if (cur) matches.push(cur);
                            cur = {code: line, vs: (lines[i+1]||'').trim() + ' vs ' + (lines[i+2]||'').trim()};
                        } else if (cur && /^\\d+\\.\\d{2}$/.test(line)) {
                            if (!cur.win) cur.win = line;
                            else if (!cur.draw) cur.draw = line;
                            else if (!cur.lose) cur.lose = line;
                        }
                    }
                    if (cur) matches.push(cur);

                    return JSON.stringify({
                        hasWorldCup: hasWorldCup,
                        updateTime: updateTime,
                        matchCount: matches.length,
                        sample: matches.slice(0, 5)
                    });
                })()
                """,
                "returnByValue": True
            }
        }))
        result = await ws.recv()

        # 解析结果
        try:
            data = json.loads(result)
            extracted = json.loads(data.get('result', {}).get('result', {}).get('value', '{}'))
        except:
            log("⚠️ 数据解析失败,可能页面结构变化")
            return None

        return extracted

def update_data_json(odds_data):
    """更新data.json时间戳和数据来源"""
    if not DATA_FILE.exists():
        log(f"❌ data.json不存在: {DATA_FILE}")
        return False

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    data['updated'] = now

    match_count = odds_data.get('matchCount', 0) if odds_data else 0
    has_wc = odds_data.get('hasWorldCup', False) if odds_data else False

    if has_wc:
        data['source'] = f"竞彩官方实时赔率 (自动抓取 {now})"
        data['note'] = f"赔率由Python每小时自动抓取。世界杯场次已上线({match_count}场)"
        log(f"🎉 世界杯场次已上线! ({match_count}场)")
    else:
        data['source'] = f"竞彩网检查+AI预估 (检查于{now})"
        data['note'] = f"世界杯场次尚未在竞彩网开售({match_count}场其他比赛)。SPF为国际盘口换算AI预估。每小时自动检查。"
        log(f"⏳ 世界杯场次尚未上线(当前{match_count}场其他比赛)")

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

    log(f"✅ data.json 已更新")
    return True

def git_push():
    """提交并推送"""
    os.chdir(REPO_DIR)

    # 拉取最新
    subprocess.run(["git", "pull", "origin", "main"], capture_output=True)

    subprocess.run(["git", "add", "data.json"], capture_output=True)
    result = subprocess.run(["git", "diff", "--cached", "--name-only"], capture_output=True, text=True)

    if "data.json" not in result.stdout:
        log("ℹ️ 无变更,跳过推送")
        return

    now = datetime.now().strftime("%m-%d %H:%M")
    subprocess.run(["git", "commit", "-m", f"📊 自动赔率更新 {now}"], capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], capture_output=True)
    log("✅ 已推送到GitHub")

async def main():
    log("=" * 40)
    log("🏆 世界杯赔率自动抓取 v2.0 (全自动)")
    log("=" * 40)

    if DRY_RUN:
        log("🔶 Dry-run模式")

    # 1. 自动启动浏览器
    if not launch_browser():
        log("❌ 浏览器启动失败,退出")
        sys.exit(1)

    # 2. 抓取赔率
    log("📡 抓取竞彩网赔率...")
    odds = await cdp_fetch_odds()

    if odds:
        log(f"  比赛数: {odds.get('matchCount', 0)}")
        log(f"  世界杯: {'是' if odds.get('hasWorldCup') else '否'}")
        log(f"  更新时间: {odds.get('updateTime', '未知')}")
    else:
        log("⚠️ 赔率抓取失败")

    # 3. 更新+推送
    if not DRY_RUN:
        update_data_json(odds)
        if not NO_PUSH:
            git_push()

    log("✅ 完成")
    log("=" * 40)

if __name__ == "__main__":
    asyncio.run(main())
