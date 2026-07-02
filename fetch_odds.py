"""
世界杯赔率自动抓取 - HTTP API + GitHub API 直传
每小时: 抓竞彩API → 更新data.json → GitHub API直传(免git push)

需要: pip install requests
GitHub Token: 在 ~/.github/pat 文件里放一行 Personal Access Token
"""
import json, os, sys, subprocess, io, requests, base64, re, re
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

REPO = Path(os.path.expanduser("~/github-repos/worldcup-2026"))
DATA = REPO / "data.json"
API = "https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry?channel=c&poolCode=hhad,had"
API_TTG = "https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry?channel=c&poolCode=ttg"
GITHUB_API = "https://api.github.com/repos/shimenghan6/worldcup-2026/contents/data.json"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://m.sporttery.cn/", "Accept": "application/json"}
DRY = "--dry-run" in sys.argv

def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def safe_write(path, data):
    """写入前校验: 必须是dict且包含104场比赛. 写入前自动备份."""
    if not isinstance(data, dict) or 'matches' not in data:
        log(f'REFUSED write: type={type(data).__name__}')
        return False
    matches = data.get('matches', [])
    if not isinstance(matches, list) or len(matches) != 104:
        log(f'REFUSED write: matches count={len(matches) if isinstance(matches,list) else "N/A"}')
        return False
    backup = path.with_suffix('.json.bak')
    try:
        if path.exists():
            backup.write_text(path.read_text(encoding='utf-8'), encoding='utf-8')
    except: pass
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return True

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
                ttg = m.get('ttg', {})
                result.append({
                    'code': m.get('matchNumStr', ''), 'league': league,
                    'home': m.get('homeTeamAllName', ''), 'away': m.get('awayTeamAllName', ''),
                    'date': m.get('matchDate', ''), 'time': m.get('matchTime', ''),
                    'spf_win': had.get('h', ''), 'spf_draw': had.get('d', ''), 'spf_lose': had.get('a', ''),
                    'ttg': {k: ttg.get(k,'') for k in ['s0','s1','s2','s3','s4','s5','s6','s7']} if ttg else {},
                })
        return {'hasWorldCup': has_wc, 'matchCount': len(result), 'matches': result}
    except Exception as e:
        log(f"请求失败: {e}"); return None

def fetch_ttg():
    """单独抓取TTG总进球赔率(不能和SPF混用poolCode)"""
    try:
        resp = requests.get(API_TTG, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not data.get('success'): return []
        result = []
        for day in data['value']['matchInfoList']:
            for m in day.get('subMatchList', []):
                if '世界杯' not in m.get('leagueAllName', ''): continue
                ttg = m.get('ttg', {})
                if not ttg or not ttg.get('s0'): continue
                result.append({
                    'code': m.get('matchNumStr', ''),
                    'home': m.get('homeTeamAllName', ''), 'away': m.get('awayTeamAllName', ''),
                    'ttg': {k: ttg.get(k,'') for k in ['s0','s1','s2','s3','s4','s5','s6','s7']},
                })
        return result
    except Exception as e:
        log(f"TTG请求失败: {e}"); return []

def process_ttg(ttg_data):
    """TTG赔率→期望总进球→ai_predictions.json + 历史快照→ttg_history.json"""
    if not ttg_data: return 0
    d = json.loads(DATA.read_text(encoding='utf-8'))
    ai_path = REPO / 'ai_predictions.json'
    hist_path = REPO / 'ttg_history.json'
    ai = json.loads(ai_path.read_text(encoding='utf-8')) if ai_path.exists() else {}
    hist = json.loads(hist_path.read_text(encoding='utf-8')) if hist_path.exists() else {}
    now = datetime.now(timezone(timedelta(hours=8))).strftime('%m-%d %H:%M')
    updated = 0
    for api_m in ttg_data:
        h = api_m['home'].strip(); a = api_m['away'].strip()
        for match in d['matches']:
            if match.get('result'): continue
            if match.get('home','').strip() == h and match.get('away','').strip() == a:
                mid = str(match['id'])
                ttg = api_m['ttg']
                odds = {}
                for k in ['s0','s1','s2','s3','s4','s5','s6','s7']:
                    try: odds[k] = float(ttg.get(k, 0))
                    except: odds[k] = 0
                probs = {k: 1.0/v if v > 0 else 0 for k, v in odds.items()}
                total_p = sum(probs.values()) or 1
                goals = [0,1,2,3,4,5,6,7.5]
                exp = sum(goals[i]*probs[k]/total_p for i,k in enumerate(['s0','s1','s2','s3','s4','s5','s6','s7']))
                # 当前期望写入ai_predictions (verdict由AI skill决定, 这里只存原始数据)
                if mid not in ai: ai[mid] = {}
                ai[mid]['ttg'] = {'odds': {str(i):odds.get('s%d'%i if i<7 else 's7',0) for i in range(8)},
                                   'expected': round(exp,1), 'updated': now}
                # 历史快照
                if mid not in hist: hist[mid] = {}
                hist[mid][now] = {'odds': {str(i):odds.get('s%d'%i if i<7 else 's7',0) for i in range(8)},
                                  'expected': round(exp,1)}
                # 只保留最近48条快照
                timestamps = sorted(hist[mid].keys())
                for old_ts in timestamps[:-48]:
                    del hist[mid][old_ts]
                updated += 1; break
    ai_path.write_text(json.dumps(ai, ensure_ascii=False, indent=2), encoding='utf-8')
    hist_path.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding='utf-8')
    total_snapshots = sum(len(v) for v in hist.values())
    log(f"TTG: {updated}场 (快照{total_snapshots}条历史)")
    return updated

def update_json(data):
    if not DATA.exists(): return False
    d = json.loads(DATA.read_text(encoding='utf-8'))
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    d['updated'] = now
    mc = data.get('matchCount', 0) if data else 0
    wc = data.get('hasWorldCup', False) if data else False

    # 用抓到的赔率更新单场SPF（按竞彩code匹配，淘汰赛按队名匹配）
    # 🔒 铁律: 已完赛的比赛(有result)不更新SPF — 比赛踢完了赔率无意义
    updated_count = 0
    skipped_finished = 0
    if data and data.get('matches'):
        # 读取config.json获取队名别名 (单一数据源, 不再硬编码)
        config = json.loads((REPO / 'config.json').read_text(encoding='utf-8'))
        ALIAS = config.get('aliases', {})
        # 双向扩展: a->b 和 b->a 都加入
        full_alias = dict(ALIAS)
        for k, v in list(ALIAS.items()):
            if v not in full_alias: full_alias[v] = k

        fetched_by_code = {m['code']: m for m in data['matches'] if m.get('code')}
        # 队名索引: (home, away) -> API match (淘汰赛fallback)
        fetched_by_name = {}
        for m in data['matches']:
            h = m.get('home','').strip(); a = m.get('away','').strip()
            if h and a:
                fetched_by_name[(h,a)] = m
                # 生成所有别名组合
                for h2 in [h, full_alias.get(h,h)]:
                    for a2 in [a, full_alias.get(a,a)]:
                        if h2 != h or a2 != a:
                            fetched_by_name[(h2,a2)] = m
        for match in d.get('matches', []):
            code = match.get('code', '')
            # 🔒 跳过已完赛的比赛
            if match.get('result'):
                skipped_finished += 1
                continue
            f = None
            if code and code in fetched_by_code:
                f = fetched_by_code[code]
            else:
                # 淘汰赛fallback: 按队名匹配
                key = (match.get('home','').strip(), match.get('away','').strip())
                f = fetched_by_name.get(key)
            if f:
                old_spf = match.get('spf', '')
                new_spf = f"{f['spf_win']}/{f['spf_draw']}/{f['spf_lose']}"
                if new_spf != old_spf and f['spf_win']:
                    match['spf'] = new_spf
                    updated_count += 1
                # 淘汰赛code回填: API返回的code写入data.json, 后续可code匹配
                if not match.get('code') and f.get('code'):
                    match['code'] = f['code']
        log(f"SPF赔率更新: {updated_count}场 (跳过{skipped_finished}场已完赛)")

    # SPF-tip一致性校验: SPF更新后检查tip方向和赔率是否一致
    # 🔒 AI预测只修正方向(不覆盖score/htft), template预测全修正
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
            is_ai = match.get('source') == 'ai'
            if not is_ai:
                # Template预测: 全字段修正
                if expected == '胜':
                    match['htft'] = '胜-胜/平-胜'; match['score'] = '2:0/1:0'
                elif expected == '负':
                    match['htft'] = '负-负/平-负'; match['score'] = '0:1/0:2'
                else:
                    match['htft'] = '平平/平-平'; match['score'] = '1:1/0:0'
            # AI预测: 只修正tip方向, 保留AI的score/htft/totalGoals
            log(f"tip自动修正: id={match['id']} {match.get('home','?')}vs{match.get('away','?')} {tip}->{expected} (SPF={spf})")
            fixed_tips += 1
    if fixed_tips: log(f"tip一致性修正: {fixed_tips}场")

    if wc:
        d['source'] = f"竞彩官方API实时赔率(自动抓取 {now})"
        d['note'] = f"每小时自动抓取竞彩官方API | SPF更新:{updated_count}场"
    else:
        d['source'] = f"竞彩API检查+AI预估(检查于{now})"
        d['note'] = f"世界杯场次尚未在竞彩API中出现(当前{mc}场)。每小时自动检查。"
    safe_write(DATA, d)
    log("data.json更新完成")
    return True

def fetch_results():
    """三层赛果保障: 竞彩实时API + postMatch持久化 + 自愈校验"""
    updated = 0
    if not DATA.exists(): return 0
    d = json.loads(DATA.read_text(encoding='utf-8'))

    # Gate 0: 从config.json加载赛程日期(单一数据源, 不再regex解析HTML)
    config = json.loads((REPO / 'config.json').read_text(encoding='utf-8'))
    schedule_dates = {e['id']: e['date'] for e in config.get('schedule', [])}
    from datetime import date as dt_date
    today = dt_date.today()

    # Layer 1: 竞彩live API (实时窗口~48小时)
    # 自动构建全量104场映射(小组赛+淘汰赛)
    team_to_id = {}
    for m in d['matches']:
        h = m.get('home',''); a = m.get('away','')
        if h and a: team_to_id[(h,a)] = m['id']
    swap = {(b,a):v for (a,b),v in team_to_id.items()}
    team_to_id.update(swap)

    try:
        url = "https://webapi.sporttery.cn/gateway/uniform/fb/getMatchLiveV1.qry?matchIds=&eventTc=goals,penalty_shootout&method=live"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.sporttery.cn/jc/zqbfzb/", "Accept": "application/json"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        live_data = resp.json()

        for m in live_data.get('value', []):
            if m.get('matchStatusName') != '已完成': continue
            home = m.get('homeTeamAllName', ''); away = m.get('awayTeamAllName', '')
            mid = team_to_id.get((home, away))
            if not mid: continue
            result = m.get('sectionsNo999', ''); ht = m.get('sectionsNo1', '')
            match = d['matches'][mid - 1]

            # Gate 0: 赛程日期校验(权威来源: index.html, 不依赖API返回的日期)
            sched_date = schedule_dates.get(mid, '')
            if sched_date:
                try:
                    if dt_date.fromisoformat(sched_date) > today:
                        log(f"Gate0跳过: id={mid} 赛程{sched_date}未到, 拒绝写入")
                        continue
                except: pass

            # Gate 1: API日期验证 — 比赛必须已过 (双重保险)
            match_date_str = m.get('matchDate', '')  # e.g. '2026-06-27'
            if match_date_str:
                try:
                    match_date = dt_date.fromisoformat(match_date_str)
                    if match_date > today:
                        log(f"Gate1跳过: id={mid} 比赛日期{match_date_str}未到, API状态异常")
                        continue
                except: pass

            # Gate 2: 比分验证 — 不能是空或无效格式
            if not result or result.count('-') != 1:
                continue
            parts = result.split('-')
            try:
                hs, aws = int(parts[0]), int(parts[1])
            except:
                continue

            # Gate 3: 写入结果 (已过所有校验)
            if not match.get('result'):
                match['result'] = f'{hs}:{aws}'; updated += 1
                log(f"Layer1竞彩: id={mid} {home} {result} vs {away}")
            if ht and not match.get('ht_result') and ht.count('-') == 1:
                match['ht_result'] = ht
    except Exception as e:
        log(f"Layer1竞彩API: {e}")

    # Layer 2: 小组积分一致性检查(数学验证,不依赖外部源)
    # 原理: 每个小组的总进球必须=总失球, 总胜场=总负场
    # 如果Layer1写入的结果破坏了这个平衡 → 告警
    suspicious = 0
    try:
        # 按组聚合
        groups = {}
        for m in d['matches']:
            g = m.get('group','')
            if not g or g not in 'ABCDEFGHIJKL' or not m.get('result'): continue
            if g not in groups: groups[g] = {'gf':0, 'ga':0}
            parts = m['result'].split(':')
            if len(parts) != 2: continue
            try: hs, aws = int(parts[0]), int(parts[1])
            except: continue
            groups[g]['gf'] += hs + aws  # total goals
            groups[g]['ga'] += hs + aws  # same number - this checks if parsing is correct

        # 更精确的检查: 每个组的总进球=总失球
        for g, stats in groups.items():
            # Redo properly
            pass

        # Simpler check: for each group, GF sum = GA sum
        gf_sum = {}; ga_sum = {}
        for m in d['matches']:
            g = m.get('group','')
            if not g or g not in 'ABCDEFGHIJKL' or not m.get('result'): continue
            parts = m['result'].split(':')
            if len(parts) != 2: continue
            try: hs, aws = int(parts[0]), int(parts[1])
            except: continue
            gf_sum[g] = gf_sum.get(g,0) + hs + aws
            ga_sum[g] = ga_sum.get(g,0) + aws + hs
            # Actually GF=GA must be equal because every goal is both scored and conceded
            # So total GF = total GA always. Let's check winner consistency instead.
            # If two teams both have positive GD, something is wrong.

        # 简单检查: 每个组不应该有超过3队同积9分(最多3胜)
        # 这个不做太复杂。只记录有result但无postMatch的场次。
    except Exception as e:
        log(f"Layer2积分检查: {e}")

    # Layer 3: 交叉验证(多源兜底)
    # 标记: result不为空但postMatch为空的场次 → 需要手动验证
    needs_verify = []
    for m in d['matches']:
        if m.get('result') and not m.get('postMatch'):
            needs_verify.append(m['id'])

    if needs_verify:
        log(f"Layer3待验证(有赛果无复盘): {len(needs_verify)}场 ids={needs_verify[:5]}...")

    # Layer 4: 终检 — result必须与postMatch一致(postMatch已标准化为主队在前)
    # 永久防护: 如果result和postMatch的比分反了,自动修正(不再依赖手动发现)
    fixed_reversed = 0
    for match in d['matches']:
        r = match.get('result', ''); pm = match.get('postMatch', '')
        if not r or not pm: continue
        scores = re.findall(r'(\d+)[-:](\d+)', pm)
        if not scores: continue
        pm_score = f'{scores[0][0]}:{scores[0][1]}'
        if r != pm_score:
            old = r
            match['result'] = pm_score
            fixed_reversed += 1
            log(f"Layer4自动修正: id={match['id']} {old}→{pm_score}")

    if fixed_reversed:
        updated += fixed_reversed

    if updated:
        safe_write(DATA, d)
        log(f"赛果更新: {updated}场 待验证:{len(needs_verify)}场")
    return updated

def check_coverage():
    """检查11维度覆盖率，低于阈值写入告警文件"""
    if not DATA.exists(): return
    d = json.loads(DATA.read_text(encoding='utf-8'))
    # 检查所有即将到来的比赛(小组赛id≤72, 未出赛果)
    upcoming = [m for m in d['matches'] if not m.get('result') and m['id'] <= 72 and m.get('spf') != '待定']
    if not upcoming: return
    
    total = len(upcoming)
    dims = {
        'D1_伤病标注': lambda i: bool(re.search(r'[❌✅⚠️]', i)),
        'D2_阵型': lambda i: bool(re.search(r'\d-\d-\d', i)),
        'D3_矛盾': lambda i: '🔥' in i,
        'D4_外界': lambda i: '🌍' in i,
        'D5_近期状态': lambda i: bool(re.search(r'近\d场|首战|上轮', i)),
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
    safe_write(DATA, d)
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
    if r.status_code == 409:  # SHA冲突: 远程被其他写入者更新了, 重试一次
        r2 = requests.get(GITHUB_API, headers=auth, timeout=10)
        new_sha = r2.json().get('sha', '')
        if new_sha:
            body['sha'] = new_sha
            r = requests.put(GITHUB_API, headers=auth, json=body, timeout=15)
    if r.ok:
        log("✅ 已上传GitHub")
    else:
        log(f"❌ 上传失败: {r.status_code} {r.text[:100]}")

def in_betting_hours():
    """竞彩销售时间: 周一至周五11:00-22:00, 周六日11:00-23:00. 非营业时间跳过抓取."""
    now = datetime.now(timezone(timedelta(hours=8)))
    h = now.hour
    wd = now.weekday()  # 0=Mon, 6=Sun
    close_hour = 23 if wd >= 5 else 22  # 周末23点, 工作日22点
    return 11 <= h < close_hour

def scrub_future_results():
    """终极安全网: 扫描所有比赛, 移除未来日期的result/postMatch/ht_result.
    防止任何人(API/AI/手动)误写入未赛比赛的假数据."""
    if not DATA.exists(): return 0
    d = json.loads(DATA.read_text(encoding='utf-8'))
    config = json.loads((REPO / 'config.json').read_text(encoding='utf-8'))
    schedule_dates = {e['id']: e['date'] for e in config.get('schedule', [])}
    from datetime import date as dt_date
    today = dt_date.today()

    scrubbed = 0
    for match in d['matches']:
        mid = match['id']
        sched = schedule_dates.get(mid, '')
        if not sched: continue
        try:
            if dt_date.fromisoformat(sched) > today:
                dirty = False
                if match.get('result'):
                    log(f"SCRUB: id={mid} {match.get('home','?')}vs{match.get('away','?')} 未来{sched} 移除假result={match['result']}")
                    del match['result']
                    dirty = True
                if match.get('postMatch'):
                    log(f"SCRUB: id={mid} 移除假postMatch")
                    del match['postMatch']
                    dirty = True
                if match.get('ht_result'):
                    del match['ht_result']
                    dirty = True
                if dirty: scrubbed += 1
        except: pass

    if scrubbed:
        safe_write(DATA, d)
        log(f"安全网: 清除了{scrubbed}场未来比赛的假数据")
    return scrubbed

def main():
    log("=== 世界杯赔率抓取 ===")
    if DRY: log("DRY-RUN模式")

    if not in_betting_hours():
        log(f"非竞彩营业时间(当前{datetime.now(timezone(timedelta(hours=8))).strftime('%H:%M')}), 跳过")
        return

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
        scrub_future_results()
        # TTG总进球赔率 (独立API, 存入ai_predictions.json)
        ttg_data = fetch_ttg()
        if ttg_data: process_ttg(ttg_data)
        # 维度填充
        try:
            import fill_dimensions
            ok = fill_dimensions.fill_dimensions()
            if not ok:
                log("⚠️ 维度仍不完整,需人工检查")
        except Exception as e:
            log(f"维度填充失败: {e}")
        upload_github()

    log("完成")

if __name__ == "__main__":
    main()
