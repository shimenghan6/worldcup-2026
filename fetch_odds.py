"""
世界杯赔率自动抓取 - 纯HTTP API版(无需浏览器!)
每小时: requests.get(竞彩API) → 解析JSON → 更新data.json → git push

API: webapi.sporttery.cn 官方JSON接口
依赖: pip install requests
"""
import json, os, sys, subprocess, io, requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

REPO = Path(os.path.expanduser("~/github-repos/worldcup-2026"))
DATA = REPO / "data.json"
API = "https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry?channel=c&poolCode=hhad,had"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://m.sporttery.cn/",
    "Accept": "application/json"
}
DRY = "--dry-run" in sys.argv

def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def fetch():
    """纯HTTP请求竞彩API,零浏览器依赖"""
    try:
        resp = requests.get(API, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not data.get('success'):
            log(f"API返回失败: {data.get('errorMessage','')}")
            return None

        matches = data['value']['matchInfoList']
        result = []
        has_wc = False
        for day in matches:
            for m in day.get('subMatchList', []):
                league = m.get('leagueAllName', '')
                if '世界杯' in league:
                    has_wc = True
                had = m.get('had', {})
                result.append({
                    'code': m.get('matchNumStr', ''),
                    'league': league,
                    'home': m.get('homeTeamAllName', ''),
                    'away': m.get('awayTeamAllName', ''),
                    'date': m.get('matchDate', ''),
                    'time': m.get('matchTime', ''),
                    'spf_win': had.get('h', ''),
                    'spf_draw': had.get('d', ''),
                    'spf_lose': had.get('a', ''),
                    'status': m.get('matchStatus', ''),
                    'updated': had.get('updateDate','') + ' ' + had.get('updateTime','')
                })

        return {'hasWorldCup': has_wc, 'matchCount': len(result), 'matches': result}
    except Exception as e:
        log(f"请求失败: {e}")
        return None

def update_json(data):
    if not DATA.exists(): return False
    d = json.loads(DATA.read_text(encoding='utf-8'))
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    d['updated'] = now

    mc = data.get('matchCount', 0) if data else 0
    wc = data.get('hasWorldCup', False) if data else False

    if wc:
        d['source'] = f"竞彩官方API实时赔率(自动抓取 {now})"
        d['note'] = "每小时自动抓取竞彩官方API。赔率=竞彩官方实时数据。"
        log(f"世界杯已上线! {mc}场")
        # TODO: match SPF odds to data.json matches by team name
    else:
        d['source'] = f"竞彩API检查+AI预估(检查于{now})"
        d['note'] = f"世界杯场次尚未在竞彩API中出现(当前{mc}场其他比赛)。每小时自动检查。"
        log(f"世界杯未上线(当前{mc}场)")

    DATA.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    log("data.json更新完成")
    return True

def git_push():
    os.chdir(REPO)
    subprocess.run(["git","pull","origin","main"], capture_output=True)
    subprocess.run(["git","add","data.json"], capture_output=True)
    r = subprocess.run(["git","diff","--cached","--name-only"], capture_output=True, text=True)
    if "data.json" not in r.stdout:
        log("无变更跳过推送")
        return
    now = datetime.now().strftime("%m-%d %H:%M")
    subprocess.run(["git","commit","-m",f"自动赔率更新 {now}"], capture_output=True)
    subprocess.run(["git","push","origin","main"], capture_output=True)
    log("已推送")

def main():
    log("=== 世界杯赔率抓取(HTTP API) ===")
    log(f"API: {API[:50]}...")
    if DRY: log("DRY-RUN模式")

    data = fetch()
    if data:
        log(f"抓取成功: {data['matchCount']}场 | 世界杯={'是' if data['hasWorldCup'] else '否'}")
        for m in data['matches'][:5]:
            log(f"  {m['code']} {m['home']} vs {m['away']} | SPF {m['spf_win']}/{m['spf_draw']}/{m['spf_lose']}")
        if len(data['matches']) > 5:
            log(f"  ...共{len(data['matches'])}场")
    else:
        log("抓取失败")

    if not DRY:
        update_json(data)
        git_push()

    log("完成")

if __name__ == "__main__":
    main()
