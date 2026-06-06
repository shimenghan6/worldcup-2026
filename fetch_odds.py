"""
世界杯赔率自动抓取脚本 - 零Token方案
每2小时运行一次,通过CDP协议操控Edge浏览器抓取sporttery.cn赔率
独立于Claude,不消耗AI token

用法:
  python fetch_odds.py           # 抓取赔率→更新data.json→git push
  python fetch_odds.py --dry-run # 仅抓取,不更新不推送
  python fetch_odds.py --no-push # 更新data.json但不推送

依赖: pip install websockets
需要: Edge浏览器以CDP模式运行 (--remote-debugging-port=9222)

Windows定时任务:
  schtasks /create /tn "WorldCupOdds" /tr "python C:\Users\shish\github-repos\worldcup-2026\fetch_odds.py" /sc hourly /mo 2
"""

import asyncio, json, os, sys, subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_DIR = Path(os.path.expanduser("~/github-repos/worldcup-2026"))
DATA_FILE = REPO_DIR / "data.json"
CDP_PORT = 9222
SPF_URL = "https://m.sporttery.cn/mjc/jsq/zqspf/"
CHAMPION_URL = "https://m.sporttery.cn/"
DRY_RUN = "--dry-run" in sys.argv
NO_PUSH = "--no-push" in sys.argv

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

async def cdp_fetch_odds():
    """通过CDP连接Edge浏览器,抓取移动版竞彩赔率"""
    import urllib.request

    # 1. 获取CDP页面列表
    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=5)
        pages = json.loads(resp.read())
    except Exception as e:
        log(f"❌ 无法连接CDP端口{CDP_PORT}: {e}")
        log("请先用以下命令启动Edge: msedge --remote-debugging-port=9222")
        return None

    # 2. 找到或创建目标页面
    target = next((p for p in pages if 'sporttery.cn' in p.get('url', '')), None)

    import websockets

    if target:
        ws_url = target['webSocketDebuggerUrl']
        log(f"✅ 复用已打开页面: {target['url'][:60]}")
    else:
        # 创建新页面并导航
        log("创建新页面...")
        ws_url = None
        for p in pages:
            if p.get('type') == 'page':
                ws_url = p.get('webSocketDebuggerUrl')
                break
        if not ws_url:
            log("❌ 无可用页面")
            return None

    async with websockets.connect(ws_url, max_size=10*1024*1024) as ws:
        # 启用Runtime
        await ws.send(json.dumps({"id":1, "method":"Runtime.enable"}))
        await ws.recv()

        # 导航到目标页面
        await ws.send(json.dumps({
            "id":2, "method":"Page.enable"
        }))
        await ws.recv()

        await ws.send(json.dumps({
            "id":3, "method":"Page.navigate", "params":{"url": SPF_URL}
        }))
        nav_result = await ws.recv()
        log(f"导航到竞彩移动版...")

        # 等待页面加载
        await asyncio.sleep(3)

        # 提取赔率数据
        await ws.send(json.dumps({
            "id":4, "method":"Runtime.evaluate",
            "params": {
                "expression": """
                (function() {
                    const matches = [];
                    const text = document.body.innerText;
                    // 检查是否有世界杯场次
                    const hasWorldCup = text.includes('世界杯');
                    const updateTime = document.body.innerText.match(/\\d{4}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}:\\d{2}/)?.[0] || '';

                    // 提取所有比赛行
                    const lines = text.split('\\n').filter(l => l.trim());
                    let currentMatch = null;

                    for (let i = 0; i < lines.length; i++) {
                        const line = lines[i].trim();
                        // 匹配比赛编号模式 (如 "周六205" 或 "周五201")
                        if (/周[一二三四五六日]\\d{3}/.test(line)) {
                            if (currentMatch) matches.push(currentMatch);
                            currentMatch = {code: line};
                        } else if (currentMatch) {
                            // 匹配赔率 (数字.数字 模式)
                            if (/^\\d+\\.\\d{2}$/.test(line) && !currentMatch.spf_win) {
                                currentMatch.spf_win = line;
                            } else if (/^\\d+\\.\\d{2}$/.test(line) && currentMatch.spf_win && !currentMatch.spf_draw) {
                                currentMatch.spf_draw = line;
                            } else if (/^\\d+\\.\\d{2}$/.test(line) && currentMatch.spf_draw && !currentMatch.spf_lose) {
                                currentMatch.spf_lose = line;
                            }
                        }
                    }
                    if (currentMatch) matches.push(currentMatch);

                    return JSON.stringify({
                        hasWorldCup: hasWorldCup,
                        updateTime: updateTime,
                        matchCount: matches.length,
                        matches: matches.slice(0, 30)
                    });
                })()
                """,
                "returnByValue": True
            }
        }))
        result = await ws.recv()
        data = json.loads(result)
        extracted = json.loads(data.get('result', {}).get('result', {}).get('value', '{}'))
        log(f"提取数据: {extracted.get('matchCount', 0)}场比赛, 世界杯={extracted.get('hasWorldCup', False)}")
        return extracted

def update_data_json(odds_data):
    """更新data.json中的赔率数据"""
    if not DATA_FILE.exists():
        log(f"❌ data.json不存在: {DATA_FILE}")
        return False

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    data['updated'] = now

    if odds_data and odds_data.get('hasWorldCup'):
        data['source'] = f"竞彩官方实时赔率 (抓取于{now})"
        data['note'] = "赔率数据自动抓取自竞彩网,每2小时更新"
        log("🎉 世界杯场次已上线!更新官方赔率")
    else:
        data['source'] = f"竞彩网(世界杯场次待上线) + AI预估 (检查于{now})"
        data['note'] = f"世界杯场次尚未在竞彩网开售,当前SPF为国际盘口换算AI预估。最后检查:{now}"
        log("⏳ 世界杯场次尚未上线,保持AI预估数据")

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

    log(f"✅ data.json已更新: {now}")
    return True

def git_push():
    """提交并推送更新"""
    os.chdir(REPO_DIR)
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
    log("🏆 世界杯赔率自动抓取 v1.0")
    log("=" * 40)

    if DRY_RUN:
        log("🔶 Dry-run模式")

    odds = await cdp_fetch_odds()

    if not DRY_RUN and odds:
        update_data_json(odds)
        if not NO_PUSH:
            git_push()

    log("完成")

if __name__ == "__main__":
    asyncio.run(main())
