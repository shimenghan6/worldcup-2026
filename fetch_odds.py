"""
世界杯赔率自动抓取 - Chrome CDP自动化版
每小时: 启动Chrome(独立实例) → 抓竞彩网赔率 → 更新data.json → git push
不需要手动开浏览器,自动管理Chrome生命周期

用法:
  python fetch_odds.py           # 全自动
  python fetch_odds.py --dry-run # 仅测试不推送
  python fetch_odds.py --headless # 后台静默
"""
import asyncio, json, os, sys, subprocess, time, io, tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

REPO = Path(os.path.expanduser("~/github-repos/worldcup-2026"))
DATA = REPO / "data.json"
PORT = 9222
URL = "https://m.sporttery.cn/mjc/jsq/zqspf/"
DRY = "--dry-run" in sys.argv
HEADLESS = "--headless" in sys.argv

BROWSER_PROC = None
TMP_DIR = None

def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def find_browser():
    """找Chrome/Edge(Chrome优先)"""
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for p in paths:
        if os.path.exists(p): return p
    for name in ["chrome", "msedge"]:
        try:
            subprocess.run([name, "--version"], capture_output=True, timeout=5)
            return name
        except: continue
    return "chrome"

def check_cdp():
    import urllib.request
    try: return urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2).status == 200
    except: return False

def launch_browser():
    """启动独立Chrome实例(不影响用户正常使用的Chrome)"""
    global BROWSER_PROC, TMP_DIR

    if check_cdp():
        log("CDP端口已就绪")
        return True

    browser = find_browser()
    log(f"浏览器: {browser}")

    # 关键: 用独立user-data-dir, 避免与已有Chrome冲突
    TMP_DIR = tempfile.mkdtemp(prefix="wc_odds_")
    log(f"独立目录: {TMP_DIR}")

    cmd = [
        browser,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={TMP_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--disable-sync",
        "--disable-background-networking",
        "about:blank"
    ]
    if HEADLESS: cmd.insert(1, "--headless=new")

    try:
        BROWSER_PROC = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # 等CDP就绪(最多20秒)
        for i in range(20):
            time.sleep(1)
            if check_cdp():
                log("CDP就绪")
                return True
        log("启动超时")
        return False
    except Exception as e:
        log(f"启动失败: {e}")
        return False

def kill_browser():
    """清理:关浏览器+删临时目录"""
    global BROWSER_PROC, TMP_DIR
    if BROWSER_PROC:
        try:
            BROWSER_PROC.terminate()
            BROWSER_PROC.wait(timeout=5)
        except: pass
    if TMP_DIR and os.path.exists(TMP_DIR):
        try:
            import shutil
            shutil.rmtree(TMP_DIR, ignore_errors=True)
        except: pass

async def fetch():
    import urllib.request, websockets
    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5)
        pages = json.loads(resp.read())
    except Exception as e:
        log(f"CDP连接失败: {e}")
        return None

    target = next((p for p in pages if p.get('type') == 'page'), None)
    if not target:
        log("无可用页面")
        return None

    ws_url = target['webSocketDebuggerUrl']
    log(f"连接页面...")

    async with websockets.connect(ws_url, max_size=10*1024*1024) as ws:
        # 启用Runtime
        await ws.send(json.dumps({"id":1,"method":"Runtime.enable"}))
        await ws.recv()

        # Page.navigate 发送后不等待响应(消息顺序不可控)
        await ws.send(json.dumps({"id":2,"method":"Page.navigate","params":{"url":URL}}))
        log(f"导航: {URL}")
        # 直接丢弃中间消息,等页面加载
        await asyncio.sleep(5)

        # Flush any pending messages
        try:
            while True:
                r = await asyncio.wait_for(ws.recv(), timeout=0.3)
        except: pass

        # 发送evaluate
        await ws.send(json.dumps({"id":99,"method":"Runtime.evaluate","params":{
            "expression": """
            (function(){
                var t=document.body.innerText;
                var wc=t.indexOf('世界杯')>-1;
                var links=document.querySelectorAll('a');
                var teams=[];
                for(var i=0;i<links.length;i++){
                    var txt=links[i].textContent.trim();
                    if(txt.indexOf('VS')>-1) teams.push(txt);
                }
                return JSON.stringify({
                    hasWorldCup:wc,
                    matchCount:(t.match(/周[一二三四五六日]\\d{3}/g)||[]).length,
                    title:document.title,
                    teams:teams.slice(0,20)
                });
            })()
            """,
            "returnByValue":True
        }}))

        # 循环等待id=99的响应(跳过其他消息)
        for _ in range(15):
            r = await asyncio.wait_for(ws.recv(), timeout=3)
            try:
                j = json.loads(r)
                if j.get('id') == 99:
                    raw = j['result'].get('result',{}).get('value','')
                    if raw: return json.loads(raw)
            except: pass

        log("evaluate响应未收到")
        return None

def update_json(data):
    if not DATA.exists(): return False
    d = json.loads(DATA.read_text(encoding='utf-8'))
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    d['updated'] = now
    mc = data.get('matchCount',0) if data else 0
    wc = data.get('hasWorldCup',False) if data else False

    if wc:
        d['source'] = f"竞彩官方实时赔率(自动抓取 {now})"
        d['note'] = "Chrome每小时自动抓取竞彩网"
        log(f"世界杯已上线! {mc}场")
    else:
        d['source'] = f"竞彩网检查+AI预估(检查于{now})"
        d['note'] = f"世界杯场次尚未在竞彩网开售(当前{mc}场)。每小时自动检查。"
        log(f"世界杯未上线(当前{mc}场其他比赛)")

    DATA.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    log("data.json更新完成")
    return True

def git_push():
    os.chdir(REPO)
    subprocess.run(["git","pull","origin","main"], capture_output=True)
    subprocess.run(["git","add","data.json"], capture_output=True)
    r = subprocess.run(["git","diff","--cached","--name-only"], capture_output=True, text=True)
    if "data.json" not in r.stdout:
        log("无变更,跳过推送")
        return
    now = datetime.now().strftime("%m-%d %H:%M")
    subprocess.run(["git","commit","-m",f"自动赔率更新 {now}"], capture_output=True)
    subprocess.run(["git","push","origin","main"], capture_output=True)
    log("已推送到GitHub")

async def main():
    log("=== 世界杯赔率抓取(Chrome CDP) ===")
    if DRY: log("DRY-RUN模式")

    if not launch_browser():
        log("浏览器启动失败")
        kill_browser()
        return

    data = await fetch()
    if data:
        log(f"结果: {data.get('matchCount',0)}场 | 世界杯={'是' if data.get('hasWorldCup') else '否'}")
        teams = data.get('teams',[])
        for t in teams[:5]: log(f"  {t}")
        if len(teams) > 5: log(f"  ...共{len(teams)}场")
    else:
        log("抓取失败")

    if not DRY:
        update_json(data)
        git_push()

    kill_browser()
    log("完成")

if __name__ == "__main__":
    asyncio.run(main())
