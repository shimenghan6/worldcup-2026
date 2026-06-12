"""
世界杯赔率自动抓取 - HTTP API + GitHub API 直传
每小时: 抓竞彩API → 更新data.json → GitHub API直传(免git push)

需要: pip install requests
GitHub Token: 在 ~/.github/pat 文件里放一行 Personal Access Token
"""
import json, os, sys, subprocess, io, requests, base64
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

REPO = Path(os.path.expanduser("~/github-repos/worldcup-2026"))
DATA = REPO / "data.json"
API = "https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry?channel=c&poolCode=hhad,had"
GITHUB_API = "https://api.github.com/repos/shimenghan6/worldcup-2026/contents/data.json"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://m.sporttery.cn/", "Accept": "application/json"}
DRY = "--dry-run" in sys.argv

def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def get_token():
    """读取GitHub PAT"""
    pat_file = Path(os.path.expanduser("~/.github/pat"))
    if pat_file.exists():
        return pat_file.read_text().strip()
    token = os.environ.get("GITHUB_TOKEN", "")
    if token: return token
    log("⚠️ 未找到GitHub Token,请创建 C:\\Users\\shish\\.github\\pat")
    return None

def fetch():
    try:
        resp = requests.get(API, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not data.get('success'): return None
        matches = data['value']['matchInfoList']
        result = []; has_wc = False
        for day in matches:
            for m in day.get('subMatchList', []):
                league = m.get('leagueAllName', '')
                if '世界杯' in league: has_wc = True
                had = m.get('had', {})
                result.append({
                    'code': m.get('matchNumStr', ''), 'league': league,
                    'home': m.get('homeTeamAllName', ''), 'away': m.get('awayTeamAllName', ''),
                    'date': m.get('matchDate', ''), 'time': m.get('matchTime', ''),
                    'spf_win': had.get('h', ''), 'spf_draw': had.get('d', ''), 'spf_lose': had.get('a', ''),
                })
        return {'hasWorldCup': has_wc, 'matchCount': len(result), 'matches': result}
    except Exception as e:
        log(f"请求失败: {e}"); return None

def update_json(data):
    if not DATA.exists(): return False
    d = json.loads(DATA.read_text(encoding='utf-8'))
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    d['updated'] = now
    mc = data.get('matchCount', 0) if data else 0
    wc = data.get('hasWorldCup', False) if data else False

    # 用抓到的赔率更新单场SPF（按竞彩code匹配）
    updated_count = 0
    if data and data.get('matches'):
        fetched = {m['code']: m for m in data['matches'] if m.get('code')}
        for match in d.get('matches', []):
            code = match.get('code', '')
            if code and code in fetched:
                f = fetched[code]
                old_spf = match.get('spf', '')
                new_spf = f"{f['spf_win']}/{f['spf_draw']}/{f['spf_lose']}"
                if new_spf != old_spf and f['spf_win']:
                    match['spf'] = new_spf
                    updated_count += 1
        log(f"SPF赔率更新: {updated_count}场")

    if wc:
        d['source'] = f"竞彩官方API实时赔率(自动抓取 {now})"
        d['note'] = f"每小时自动抓取竞彩官方API | SPF更新:{updated_count}场"
    else:
        d['source'] = f"竞彩API检查+AI预估(检查于{now})"
        d['note'] = f"世界杯场次尚未在竞彩API中出现(当前{mc}场)。每小时自动检查。"
    DATA.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    log("data.json更新完成")
    return True

def fetch_results():
    """从FIFA API抓取世界杯赛果,写入data.json"""
    from datetime import date, timedelta
    start = (date.today() - timedelta(days=1)).isoformat()
    end = (date.today() + timedelta(days=2)).isoformat()
    url = f"https://api.fifa.com/api/v3/calendar/matches?from={start}T00:00:00Z&to={end}T23:59:59Z&language=en&count=100"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log(f"FIFA API请求失败: {e}")
        return 0

    # (FIFA英文名, 对手英文名) → match id
    team_to_id = {
        ('Mexico','South Africa'):1, ('Korea Republic','Czechia'):2,
        ('Canada','Bosnia and Herzegovina'):3, ('United States','Paraguay'):4,
        ('Qatar','Switzerland'):5, ('Brazil','Morocco'):6,
        ('Haiti','Scotland'):7, ('Australia','Turkiye'):8,
        ('Germany','Curacao'):9, ('Netherlands','Japan'):10,
        ("Cote d'Ivoire",'Ecuador'):11, ('Sweden','Tunisia'):12,
        ('Spain','Cabo Verde'):13, ('Belgium','Egypt'):14,
        ('Saudi Arabia','Uruguay'):15, ('Iran','New Zealand'):16,
        ('France','Senegal'):17, ('Iraq','Norway'):18,
        ('Argentina','Algeria'):19, ('Austria','Jordan'):20,
        ('Portugal','DR Congo'):21, ('England','Croatia'):22,
        ('Ghana','Panama'):23, ('Uzbekistan','Colombia'):24,
    }
    # Support swapped home/away
    swap = {(b,a):v for (a,b),v in team_to_id.items()}
    team_to_id.update(swap)

    if not DATA.exists(): return 0
    d = json.loads(DATA.read_text(encoding='utf-8'))
    updated = 0

    for m in data.get('Results', []):
        stage = [s.get('Description','') for s in (m.get('StageName') or [])]
        if 'First Stage' not in stage: continue
        if m.get('MatchStatus') not in (0, 3): continue
        hs = m.get('HomeTeamScore')
        as_ = m.get('AwayTeamScore')
        if hs is None or as_ is None: continue

        home_en = (m.get('Home') or {}).get('TeamName',[{}])[0].get('Description','')
        away_en = (m.get('Away') or {}).get('TeamName',[{}])[0].get('Description','')
        mid = team_to_id.get((home_en, away_en))
        if not mid: continue

        result = f"{hs}-{as_}"
        match = d['matches'][mid-1]
        if not match.get('result'):
            match['result'] = result
            updated += 1
            log(f"赛果: {home_en} {hs}-{as_} {away_en} (id={mid})")

    if updated:
        DATA.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
        log(f"赛果更新: {updated}场")
    return updated

def upload_github():
    """通过GitHub REST API直传data.json(免git)"""
    token = get_token()
    if not token:
        log("❌ 无Token,跳过上传")
        return

    content = DATA.read_text(encoding='utf-8')
    encoded = base64.b64encode(content.encode('utf-8')).decode('ascii')
    auth = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    # Get current sha
    r = requests.get(GITHUB_API, headers=auth, timeout=10)
    sha = r.json().get('sha', '') if r.ok else ''

    # PUT update
    now = datetime.now().strftime("%m-%d %H:%M")
    body = {"message": f"📊 自动赔率更新 {now}", "content": encoded}
    if sha: body['sha'] = sha

    r = requests.put(GITHUB_API, headers=auth, json=body, timeout=15)
    if r.ok:
        log("✅ 已上传GitHub")
    else:
        log(f"❌ 上传失败: {r.status_code} {r.text[:100]}")

def main():
    log("=== 世界杯赔率抓取 ===")
    if DRY: log("DRY-RUN模式")

    data = fetch()
    if data:
        log(f"抓取: {data['matchCount']}场 | 世界杯={'是' if data['hasWorldCup'] else '否'}")
        for m in data['matches'][:3]:
            log(f"  {m['home']} vs {m['away']} | {m['spf_win']}/{m['spf_draw']}/{m['spf_lose']}")
    else:
        log("抓取失败")

    if not DRY:
        update_json(data)
        fetch_results()
        upload_github()

    log("完成")

if __name__ == "__main__":
    main()
