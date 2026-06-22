"""
世界杯赔率自动抓取 - HTTP API + GitHub API 直传
每小时: 抓竞彩API → 更新data.json → GitHub API直传(免git push)

需要: pip install requests
GitHub Token: 在 ~/.github/pat 文件里放一行 Personal Access Token
"""
import json, os, sys, subprocess, io, requests, base64, re
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
    # 🔒 铁律: 已完赛的比赛(有result)不更新SPF — 比赛踢完了赔率无意义
    updated_count = 0
    skipped_finished = 0
    if data and data.get('matches'):
        fetched = {m['code']: m for m in data['matches'] if m.get('code')}
        for match in d.get('matches', []):
            code = match.get('code', '')
            # 🔒 跳过已完赛的比赛
            if match.get('result'):
                skipped_finished += 1
                continue
            if code and code in fetched:
                f = fetched[code]
                old_spf = match.get('spf', '')
                new_spf = f"{f['spf_win']}/{f['spf_draw']}/{f['spf_lose']}"
                if new_spf != old_spf and f['spf_win']:
                    match['spf'] = new_spf
                    updated_count += 1
        log(f"SPF赔率更新: {updated_count}场 (跳过{skipped_finished}场已完赛)")

    # SPF-tip一致性校验: SPF更新后检查tip是否和赔率一致
    fixed_tips = 0
    for match in d.get('matches', []):
        spf = match.get('spf', '')
        tip = match.get('tip', '')
        if not spf or not tip or spf == '待定' or tip == '待定': continue
        parts = spf.split('/')
        if len(parts) != 3: continue
        try: h, draw, a = float(parts[0]), float(parts[1]), float(parts[2])
        except: continue
        expected = '胜' if h <= min(draw, a) else ('负' if a <= min(h, draw) else '平')
        if tip != expected:
            match['tip'] = expected
            # Also fix derived fields to match
            if expected == '胜':
                match['htft'] = '胜-胜/平-胜'
                match['score'] = '2:0/1:0'
            elif expected == '负':
                match['htft'] = '负-负/平-负'
                match['score'] = '0:1/0:2'
            log(f"tip自动修正: id={match['id']} {match.get('home','?')}vs{match.get('away','?')} {tip}->{expected} (SPF={spf})")
            fixed_tips += 1
    if fixed_tips: log(f"tip一致性修正: {fixed_tips}场")

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
    """从 worldcup26.ir API 抓取全部赛果(覆盖整个赛事,无时间窗口限制) + 竞彩API兜底"""
    import re
    updated = 0
    if not DATA.exists(): return 0
    d = json.loads(DATA.read_text(encoding='utf-8'))

    # === 主源: worldcup26.ir (全赛事覆盖, 40+场) ===
    try:
        resp = requests.get("https://worldcup26.ir/get/games", headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        wc_data = resp.json()
        games = wc_data.get('games', wc_data)
        if isinstance(games, dict): games = list(games.values())
        
        for g in games:
            if str(g.get('finished', '')).upper() != 'TRUE': continue
            gid = int(g.get('id', 0))
            if gid < 1 or gid > 104: continue
            match = d['matches'][gid - 1]
            hs = g.get('home_score', ''); aws = g.get('away_score', '')
            if hs == '' or aws == '' or hs is None or aws is None: continue
            result = f'{hs}-{aws}'
            
            # Also get half-time from scorers field (format varies)
            changed = False
            if not match.get('result') or match.get('result') != result.replace('-', ':'):
                match['result'] = result.replace('-', ':')
                changed = True
            if changed:
                updated += 1
                log(f"worldcup26赛果: id={gid} {result}")
        log(f"worldcup26.ir赛果更新: {updated}场")
    except Exception as e:
        log(f"worldcup26.ir API失败: {e}")

    # === 兜底: 竞彩 live API (最近几场) ===
    try:
        url = "https://webapi.sporttery.cn/gateway/uniform/fb/getMatchLiveV1.qry?matchIds=&eventTc=goals,penalty_shootout&method=live"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.sporttery.cn/jc/zqbfzb/", "Accept": "application/json"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        live_data = resp.json()
        
        team_to_id = {
            ('墨西哥','南非'):1, ('韩国','捷克'):2, ('加拿大','波黑'):3, ('美国','巴拉圭'):4,
            ('卡塔尔','瑞士'):5, ('巴西','摩洛哥'):6, ('海地','苏格兰'):7, ('澳大利亚','土耳其'):8,
            ('德国','库拉索'):9, ('荷兰','日本'):10, ('科特迪瓦','厄瓜多尔'):11, ('瑞典','突尼斯'):12,
            ('西班牙','佛得角'):13, ('比利时','埃及'):14, ('沙特阿拉伯','乌拉圭'):15, ('伊朗','新西兰'):16,
            ('法国','塞内加尔'):17, ('伊拉克','挪威'):18, ('阿根廷','阿尔及利亚'):19, ('奥地利','约旦'):20,
            ('葡萄牙','民主刚果'):21, ('英格兰','克罗地亚'):22, ('加纳','巴拿马'):23, ('乌兹别克斯坦','哥伦比亚'):24,
        }
        swap = {(b,a):v for (a,b),v in team_to_id.items()}
        team_to_id.update(swap)
        
        for m in live_data.get('value', []):
            if m.get('matchStatusName') != '已完成': continue
            home = m.get('homeTeamAllName', ''); away = m.get('awayTeamAllName', '')
            mid = team_to_id.get((home, away))
            if not mid: continue
            result = m.get('sectionsNo999', ''); ht = m.get('sectionsNo1', '')
            match = d['matches'][mid - 1]
            changed = False
            if result and not match.get('result'):
                match['result'] = result; changed = True
            if ht and not match.get('ht_result'):
                match['ht_result'] = ht; changed = True
            if changed:
                updated += 1
                log(f"竞彩赛果: {home} {result} (HT:{ht}) vs {away} (id={mid})")
    except Exception as e:
        log(f"竞彩赛果API: {e}")

    if updated:
        DATA.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
        log(f"赛果更新总计: {updated}场")
    return updated

def check_coverage():
    """检查11维度覆盖率，低于阈值写入告警文件"""
    if not DATA.exists(): return
    d = json.loads(DATA.read_text(encoding='utf-8'))
    upcoming = [m for m in d['matches'] if not m.get('result') and m['id'] <= 72 and m.get('spf') != '待定']
    if not upcoming: return
    
    total = len(upcoming)
    dims = {
        'D1_伤病标注': lambda i: bool(re.search(r'[❌✅⚠️]', i)),
        'D2_阵型': lambda i: bool(re.search(r'\d-\d-\d', i)),
        'D3_矛盾': lambda i: '🔥' in i,
        'D4_外界': lambda i: '🌍' in i,
        'D5_近5场': lambda i: bool(re.search(r'近\d场', i)),
        'D6_H2H': lambda i: 'H2H' in i,
        'D7_排名': lambda i: bool(re.search(r'#\d+', i)),
        'D8_位置': lambda i: bool(re.search(r'[🅕🅜🅓🅖]', i)),
        'D10_双向': lambda i: '|' in i and i.count('|') >= 3,
        'D11_上轮': lambda i: bool(re.search(r'上轮|首轮|首战', i)),
    }
    
    results = {}
    for name, check in dims.items():
        count = sum(1 for m in upcoming if m.get('injury') and check(m['injury']))
        pct = count / total * 100 if total else 0
        results[name] = pct
    
    weak = [f'{k}={v:.0f}%' for k, v in results.items() if v < 50]
    avg = sum(results.values()) / len(results)
    
    alert_file = REPO / '.needs_ai_refresh'
    if weak or avg < 60:
        msg = f"维度覆盖率告警: 平均{avg:.0f}% | 弱项: {', '.join(weak)}"
        alert_file.write_text(msg, encoding='utf-8')
        log(f"🔴 {msg}")
    elif alert_file.exists():
        alert_file.unlink()
        log("🟢 维度覆盖率恢复")
    
    d['dimension_coverage'] = {k: f'{v:.0f}%' for k, v in results.items()}
    DATA.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    log(f"维度覆盖: 平均{avg:.0f}% (弱项:{len(weak)}项)")
    return avg < 60  # returns True if needs AI refresh

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
        needs_ai = check_coverage()
        if needs_ai:
            log("⚠️ 维度覆盖率不足! 运行lottery-analyzer刷新预测")
        upload_github()

    log("完成")

if __name__ == "__main__":
    main()
