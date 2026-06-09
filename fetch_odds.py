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
        upload_github()

    log("完成")

if __name__ == "__main__":
    main()
