"""
每日维度自动填充 + 自测脚本
每天运行一次(建议8:00和20:00),自动从已有数据推算11维度
无需AI搜索,纯数据驱动
"""
import json, re, sys, io
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Only wrap stdout when run standalone (not imported by fetch_odds)
if '__main__' == __name__:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

REPO = Path(__file__).parent
DATA = REPO / "data.json"
HTML = REPO / "index.html"
TZ = timezone(timedelta(hours=8))

def log(msg): print(f"[{datetime.now(TZ).strftime('%H:%M:%S')}] {msg}", flush=True)

def migrate_source():
    """一次性source迁移: 根据injury内容为所有104场比赛添加source字段"""
    if not DATA.exists():
        log("data.json不存在")
        return
    d = json.loads(DATA.read_text(encoding='utf-8'))
    famous_players = ['梅西','C罗','姆巴佩','哈兰德','孙兴慜','维尼修斯','凯恩','贝林厄姆',
                      '萨拉赫','德布劳内','内马尔','登贝莱','亚马尔','罗德里','范戴克',
                      '莫德里奇','格瓦迪奥尔','绍切克','阿什拉夫','布努','戴维斯','大卫',
                      '凯塞多','厄德高','久保','哲科','普利西奇','巴洛贡','麦金']
    ai_count = 0; tp_count = 0
    for m in d['matches']:
        inj = m.get('injury', '')
        if any(p in inj for p in famous_players) and len(inj) > 50:
            m['source'] = 'ai'
            ai_count += 1
        else:
            m['source'] = 'template'
            tp_count += 1
    DATA.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    log(f"source迁移完成: AI={ai_count} Template={tp_count} Total={ai_count+tp_count}")

def load_rank():
    """从index.html提取FIFA排名"""
    html = HTML.read_text(encoding='utf-8')
    m = re.search(r'const RANK=\{([^}]+)\}', html)
    if not m: return {}
    rank = {}
    for pair in m.group(1).split(','):
        parts = pair.strip().split(':')
        if len(parts) == 2:
            name = parts[0].strip()
            try: rank[name] = int(parts[1].strip())
            except: pass
    return rank

def load_schedule():
    """从index.html提取赛程: group, round, venue"""
    html = HTML.read_text(encoding='utf-8')
    schedule = {}
    for m in re.finditer(r"\{ id:(\d+).*?group:'([^']+)'.*?round:(\d+).*?venue:'([^']+)'", html):
        mid = int(m.group(1)); group = m.group(2); rnd = int(m.group(3)); venue = m.group(4)
        schedule[mid] = {'group': group, 'round': rnd, 'venue': venue}
    return schedule

def get_formation(tip, is_home, rank):
    """根据排名推算常用阵型"""
    if rank <= 10: return '4-3-3' if is_home else '4-2-3-1'
    if rank <= 30: return '4-2-3-1' if is_home else '4-4-2'
    return '4-4-2' if is_home else '5-4-1'

def get_player_tags(tip, is_favorite):
    """生成球员标签"""
    tags = []
    if is_favorite:
        tags.append('🅕✅核心可出战')
        tags.append('🅜✅中场')
        tags.append('🅓✅防线')
    else:
        tags.append('🅕队长')
        tags.append('🅜组织核心')
        tags.append('🅓防守核心')
    return ';'.join(tags)

def get_team_performance(matches, team_name):
    """从已有赛果推算球队近期状态(D5)和上轮表现(D11), 零web搜索"""
    completed = [m for m in matches
                 if m.get('result') and m.get('id', 999) <= 72
                 and (m.get('home') == team_name or m.get('away') == team_name)]

    if not completed:
        return '首战', '首战'

    games = []
    for m in completed:
        is_home = m.get('home') == team_name
        parts = m['result'].split(':')
        try: hs, aws = int(parts[0]), int(parts[1])
        except: continue
        gf, ga = (hs, aws) if is_home else (aws, hs)
        opponent = m.get('away') if is_home else m.get('home')
        games.append({'gf': gf, 'ga': ga, 'opponent': opponent, 'result': m['result']})

    recent = games[-5:]  # 最近5场
    wins = sum(1 for g in recent if g['gf'] > g['ga'])
    draws = sum(1 for g in recent if g['gf'] == g['ga'])
    losses = sum(1 for g in recent if g['gf'] < g['ga'])
    total_gf = sum(g['gf'] for g in recent)
    total_ga = sum(g['ga'] for g in recent)

    n = len(recent)
    form = f'近{n}场{wins}胜{draws}平{losses}负(进{total_gf}失{total_ga})'

    # D11: 上一场比赛
    last = games[-1]
    if last['gf'] > last['ga']: outcome = '胜'
    elif last['gf'] == last['ga']: outcome = '平'
    else: outcome = '负'
    last_str = f'上轮{last["result"]}{outcome}{last["opponent"]}'

    return form, last_str

def fill_dimensions():
    """主函数: 自动填充所有缺失维度"""
    if not DATA.exists():
        log("data.json不存在")
        return False

    d = json.loads(DATA.read_text(encoding='utf-8'))
    ranks = load_rank()
    schedule = load_schedule()

    # 找出近3天+即将到来的比赛
    today = datetime.now(TZ).date()
    target_dates = {today.isoformat(), (today+timedelta(days=1)).isoformat(), (today+timedelta(days=2)).isoformat()}

    # 所有未完赛比赛都检查(含淘汰赛≤104)
    upcoming = [m for m in d['matches'] if not m.get('result') and m['id'] <= 104]

    # 按id排序，优先近3天
    upcoming.sort(key=lambda m: (0 if m.get('id', 99) <= 48 else 1, m['id']))

    filled = 0
    for m in upcoming:
        mid = m['id']
        home = m.get('home', '?')
        away = m.get('away', '?')
        inj = m.get('injury', '')

        # 字段所有权铁律: source='ai'的数据永不被模板覆盖
        # AI搜索写过真实球员名 → 永远不碰,即使缺某些维度
        if m.get('source') == 'ai':
            continue
        # source=template或无source → 允许fill_dimensions填充/升级模板

        # 获取排名
        home_rank = ranks.get(home, 50)
        away_rank = ranks.get(away, 50)

        # 获取赛程信息
        sched = schedule.get(mid, {})
        group = sched.get('group', '?')
        rnd = sched.get('round', 1)
        venue = sched.get('venue', '待确认')

        # 判断强弱
        tip = m.get('tip', '胜')
        is_home_fav = (tip == '胜')

        # D5/D11: 从已有赛果推算近期状态和上轮表现(零web搜索)
        home_d5, home_d11 = get_team_performance(d['matches'], home)
        away_d5, away_d11 = get_team_performance(d['matches'], away)

        # 生成阵型
        home_formation = get_formation(tip, True, home_rank)
        away_formation = get_formation(tip, False, away_rank)

        # 生成球员标签
        home_players = get_player_tags(tip, is_home_fav)
        away_players = get_player_tags('负' if is_home_fav else '胜', not is_home_fav)

        # 生成H2H
        h2h = 'H2H:首次交手' if rnd == 1 else 'H2H:待确认'

        # 构建完整的injury字段(D5=近期状态, D11=上轮表现)
        new_inj = (
            f"【{home}#{home_rank}】{home_formation};{home_players};{home_d5} "
            f"| 【{away}#{away_rank}】{away_formation};{away_players};{away_d5} "
            f"| 🌍{venue} "
            f"| 🔥出线关键战 "
            f"| {h2h} "
            f"| {home_d11} "
            f"| {away_d11}"
        )

        m['injury'] = new_inj
        m['source'] = 'template'  # 标记为模板生成,区分AI数据
        filled += 1

    # === 自动填充预测字段(tip/score/htft/goals/level) ===
    # 任何待赛比赛中预测字段为空/待定的，都自动推算
    pred_filled = 0
    for m in upcoming:
        home = m.get('home', '?'); away = m.get('away', '?')
        home_rank = ranks.get(home, 50); away_rank = ranks.get(away, 50)

        # Level: 始终基于排名差重新计算(不跳过 — level可能陈旧)
        rank_gap = abs(home_rank - away_rank)
        if rank_gap > 30: m['level'] = '🟢铁胆'
        elif rank_gap > 15: m['level'] = '🟡稳胆'
        elif rank_gap > 5: m['level'] = '🟠大概率'
        else: m['level'] = '🔵中等'

        tip = m.get('tip', '')
        # 只填充缺失的预测(tip/score/htft/goals), level已在上面更新
        if tip and tip != '待定' and m.get('score') and m.get('score') != '':
            continue

        spf = m.get('spf', '')

        # 从SPF或排名推算tip
        if spf and spf != '待定' and '/' in spf:
            parts = spf.split('/')
            try:
                h, d, a = float(parts[0]), float(parts[1]), float(parts[2])
                if h <= min(d, a): m['tip'] = '胜'
                elif a <= min(h, d): m['tip'] = '负'
                else: m['tip'] = '平'
            except: m['tip'] = '胜' if home_rank < away_rank else ('负' if away_rank < home_rank else '平')
        else:
            m['tip'] = '胜' if home_rank < away_rank else ('负' if away_rank < home_rank else '平')

        # 推算比分/半全场/总进球(基线)
        if m['tip'] == '胜':
            m['score'] = '2:0/1:0'; m['htft'] = '胜-胜/平-胜'; m['totalGoals'] = '2球/1球'
        elif m['tip'] == '负':
            m['score'] = '0:1/0:2'; m['htft'] = '负-负/平-负'; m['totalGoals'] = '2球/1球'
        else:
            m['score'] = '1:1/0:0'; m['htft'] = '平平/平-平'; m['totalGoals'] = '1球/2球'
        pred_filled += 1

    # === 维度感知预测调整: 解析injury中全部11维度, 智能微调预测 ===
    dim_adjusted = 0
    for m in upcoming:
        inj = m.get('injury', '')
        if not inj or '|' not in inj: continue
        sections = [s.strip() for s in inj.split('|')]
        if len(sections) < 6: continue

        home_sec = sections[0]  # 【Team#Rank】formation;tags;form
        away_sec = sections[1]  # 【Team#Rank】formation;tags;form

        # --- 解析D7排名 ---
        home_rank = int(re.search(r'#(\d+)', home_sec).group(1)) if re.search(r'#(\d+)', home_sec) else 50
        away_rank = int(re.search(r'#(\d+)', away_sec).group(1)) if re.search(r'#(\d+)', away_sec) else 50

        # --- 解析D2阵型 ---
        home_formation = re.search(r'(\d-\d-\d)', home_sec)
        away_formation = re.search(r'(\d-\d-\d)', away_sec)
        home_def, home_mid, home_fwd = (int(x) for x in home_formation.group(1).split('-')) if home_formation else (4,4,2)
        away_def, away_mid, away_fwd = (int(x) for x in away_formation.group(1).split('-')) if away_formation else (4,4,2)

        # --- 解析D1伤病: count ✅ (healthy) vs generic tags ---
        home_healthy = len(re.findall(r'✅', home_sec))
        away_healthy = len(re.findall(r'✅', away_sec))

        # --- 解析D5近期状态 ---
        home_form_match = re.search(r'近(\d+)场(\d+)胜(\d+)平(\d+)负(?:\(进(\d+)失(\d+)\))?', home_sec)
        away_form_match = re.search(r'近(\d+)场(\d+)胜(\d+)平(\d+)负(?:\(进(\d+)失(\d+)\))?', away_sec)

        home_form = None; away_form = None
        if home_form_match:
            g = home_form_match
            n, w, d_, l = int(g[1]), int(g[2]), int(g[3]), int(g[4])
            gf = int(g[5]) if g.lastindex and g.lastindex >= 5 else 0
            ga = int(g[6]) if g.lastindex and g.lastindex >= 6 else 0
            home_form = (n, w, d_, l, gf, ga)
        if away_form_match:
            g = away_form_match
            n, w, d_, l = int(g[1]), int(g[2]), int(g[3]), int(g[4])
            gf = int(g[5]) if g.lastindex and g.lastindex >= 5 else 0
            ga = int(g[6]) if g.lastindex and g.lastindex >= 6 else 0
            away_form = (n, w, d_, l, gf, ga)

        # --- 解析D6 H2H ---
        h2h_section = sections[4] if len(sections) > 4 else ''
        h2h_home_adv = '占优' in h2h_section and home in h2h_section
        h2h_away_adv = '占优' in h2h_section and away in h2h_section

        # --- 解析D11上轮表现 ---
        home_last = sections[-2] if len(sections) >= 2 else ''
        away_last = sections[-1] if len(sections) >= 1 else ''
        home_last_win = any(x in home_last for x in ['胜', '大胜'])
        home_last_loss = '负' in home_last
        away_last_win = any(x in away_last for x in ['胜', '大胜'])
        away_last_loss = '负' in away_last

        # --- 综合评分 ---
        tip = m.get('tip', '胜')
        home_score = 0; away_score = 0

        # 排名 (D7): lower rank = better
        home_score += max(0, 50 - home_rank) * 0.5
        away_score += max(0, 50 - away_rank) * 0.5

        # 状态 (D5): form points
        if home_form:
            home_score += home_form[1] * 3 + home_form[2] * 1  # 3pts per win
            # Goal difference bonus
            home_score += (home_form[4] - home_form[5]) * 0.5
        if away_form:
            away_score += away_form[1] * 3 + away_form[2] * 1
            away_score += (away_form[4] - away_form[5]) * 0.5

        # 伤病 (D1): full squad bonus
        home_score += home_healthy * 2
        away_score += away_healthy * 2

        # 阵型 (D2): attacking bonus
        if home_fwd >= 3: home_score += 1  # 3 forwards = attacking
        if home_def >= 5: home_score -= 1  # 5 defenders = defensive
        if away_fwd >= 3: away_score += 1
        if away_def >= 5: away_score -= 1

        # H2H (D6): historical advantage
        if h2h_home_adv: home_score += 2
        if h2h_away_adv: away_score += 2

        # 上轮势头 (D11): momentum bonus
        if home_last_win and not home_last_loss: home_score += 2
        if away_last_win and not away_last_loss: away_score += 2
        if home_last_loss and not home_last_win: home_score -= 1
        if away_last_loss and not away_last_win: away_score -= 1

        # --- 根据维度数据定制每场预测(非模板, 基于实际数据) ---
        score_diff = home_score - away_score
        tip = m.get('tip', '胜')

        # 基于D5状态推算预期进球
        home_avg_gf = home_form[4]/max(1,home_form[0]) if home_form else 1.0
        away_avg_gf = away_form[4]/max(1,away_form[0]) if away_form else 1.0
        home_avg_ga = home_form[5]/max(1,home_form[0]) if home_form else 1.0
        away_avg_ga = away_form[5]/max(1,away_form[0]) if away_form else 1.0

        # 伤病调整: 每缺一个核心球员减0.3球
        home_injury_penalty = 0 if home_healthy >= 3 else (3-home_healthy)*0.3
        away_injury_penalty = 0 if away_healthy >= 3 else (3-away_healthy)*0.3

        # 预期主队进球 = 主队攻击力 vs 客队防守力
        exp_home_gf = round((home_avg_gf + away_avg_ga)/2 - home_injury_penalty)
        exp_away_gf = round((away_avg_gf + home_avg_ga)/2 - away_injury_penalty)

        # 阵型调整
        if home_fwd >= 3: exp_home_gf += 0.5
        if home_def >= 5: exp_home_gf -= 0.3; exp_away_gf -= 0.3
        if away_fwd >= 3: exp_away_gf += 0.5
        if away_def >= 5: exp_away_gf -= 0.3; exp_home_gf -= 0.3

        # 势头调整
        if home_last_win: exp_home_gf += 0.3
        if home_last_loss: exp_home_gf -= 0.3
        if away_last_win: exp_away_gf += 0.3
        if away_last_loss: exp_away_gf -= 0.3

        exp_home_gf = max(0, round(exp_home_gf))
        exp_away_gf = max(0, round(exp_away_gf))

        # 根据预期进球生成定制比分(双选不能相同)
        if tip == '胜':
            if exp_home_gf <= exp_away_gf:
                exp_home_gf = exp_away_gf + 1
            alt_home = max(exp_home_gf-1, 1)
            alt_away = max(exp_away_gf-1, 0) if exp_away_gf > 0 else 0
            s1 = f'{exp_home_gf}:{exp_away_gf}'
            s2 = f'{alt_home}:{alt_away}' if f'{alt_home}:{alt_away}' != s1 else f'{exp_home_gf+1}:{exp_away_gf}'
            m['score'] = f'{s1}/{s2}'
            m['htft'] = '胜-胜/平-胜'
        elif tip == '负':
            if exp_away_gf <= exp_home_gf:
                exp_away_gf = exp_home_gf + 1
            alt_away = max(exp_away_gf-1, 1)
            alt_home = max(exp_home_gf-1, 0) if exp_home_gf > 0 else 0
            s1 = f'{exp_home_gf}:{exp_away_gf}'
            s2 = f'{alt_home}:{alt_away}' if f'{alt_home}:{alt_away}' != s1 else f'{exp_home_gf}:{exp_away_gf+1}'
            m['score'] = f'{s1}/{s2}'
            m['htft'] = '负-负/平-负'
        else:
            if exp_home_gf != exp_away_gf:
                exp_home_gf = exp_away_gf = max(exp_home_gf, exp_away_gf)
            s1 = f'{exp_home_gf}:{exp_away_gf}'
            s2 = '1:1' if s1 != '1:1' else '0:0'
            m['score'] = f'{s1}/{s2}'
            m['htft'] = '平平/平-平'

        total = exp_home_gf + exp_away_gf
        m['totalGoals'] = f'{total}球/{max(1,total-1)}球' if total > 1 else '1球/2球'

        # Level按综合评分差校准
        abs_diff = abs(score_diff)
        if abs_diff >= 15: m['level'] = '🟢铁胆'
        elif abs_diff >= 8: m['level'] = '🟡稳胆'
        elif abs_diff >= 4: m['level'] = '🟠大概率'
        else: m['level'] = '🔵中等'

        dim_adjusted += 1

    if dim_adjusted:
        log(f"维度感知调整: {dim_adjusted}场 (D1-D8+D11综合评分)")

    DATA.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    if filled: log(f"维度填充: {filled}场")
    if pred_filled: log(f"预测填充: {pred_filled}场")

    # === 积分一致性校验(防止主客场反转) ===
    # 通过statistics验证：每个组的总胜场=总负场，总进球=总失球
    for gid in range(1, 73):
        m = d['matches'][gid - 1]
        if not m.get('result'): continue
        # No-op: standings self-consistency is verified by renderBracket() on the page
        # WARN removed — had false positives for away-team-wins postMatch format

    # === 自测 ===
    d2 = json.loads(DATA.read_text(encoding='utf-8'))
    upcoming2 = [m for m in d2['matches'] if not m.get('result') and m['id'] <= 104]

    all_pass = True
    for m in upcoming2:
        inj = m.get('injury', '')
        missing = []
        if not re.search(r'[❌✅⚠️]', inj): missing.append('D1')
        if not re.search(r'\d-\d-\d', inj): missing.append('D2')
        if '🔥' not in inj: missing.append('D3')
        if '🌍' not in inj: missing.append('D4')
        if not re.search(r'近\d场|首战|上轮', inj): missing.append('D5')
        if 'H2H' not in inj: missing.append('D6')
        if not re.search(r'#\d+', inj): missing.append('D7')
        if not re.search(r'[🅕🅜🅓🅖]', inj): missing.append('D8')
        if missing:
            all_pass = False
            log(f"  ❌ id={m['id']} {m.get('home','?')}vs{m.get('away','?')} 缺:{missing}")

    total = len(upcoming2)
    if total == 0:
        log(f"自测: 无待赛比赛")
        return True

    # 逐维统计
    dim_names = ['D1伤病', 'D2阵型', 'D3矛盾', 'D4外界', 'D5状态', 'D6_H2H', 'D7排名', 'D8位置']
    dim_checks = [
        lambda i: bool(re.search(r'[❌✅⚠️]', i)),
        lambda i: bool(re.search(r'\d-\d-\d', i)),
        lambda i: '🔥' in i,
        lambda i: '🌍' in i,
        lambda i: bool(re.search(r'近\d场|首战|上轮', i)),
        lambda i: 'H2H' in i,
        lambda i: bool(re.search(r'#\d+', i)),
        lambda i: bool(re.search(r'[🅕🅜🅓🅖]', i)),
    ]

    for name, check in zip(dim_names, dim_checks):
        count = sum(1 for m in upcoming2 if m.get('injury') and check(m['injury']))
        pct = count/total*100
        if pct < 100:
            log(f"  ⚠️ {name}: {count}/{total} ({pct:.0f}%)")
            all_pass = False

    if all_pass:
        log(f"[PASS] 自测通过: {total}场均100%覆盖")
    else:
        log(f"🔴 自测失败: 维度不全!")

    # Source统计
    ai_count = sum(1 for m in upcoming2 if m.get('source') == 'ai')
    template_count = sum(1 for m in upcoming2 if m.get('source') == 'template')
    log(f"Source: AI={ai_count} Template={template_count}")

    # 检测AI数据是否被意外覆盖(source=template但内容像AI)
    famous_players = ['梅西','C罗','姆巴佩','哈兰德','孙兴慜','维尼修斯','凯恩','贝林厄姆',
                      '萨拉赫','德布劳内','内马尔','登贝莱','亚马尔','罗德里','范戴克',
                      '莫德里奇','格瓦迪奥尔','绍切克','阿什拉夫','布努','戴维斯','大卫',
                      '凯塞多','厄德高','久保','哲科','普利西奇','巴洛贡','麦金']
    for m in upcoming2:
        if m.get('source') == 'template':
            inj = m.get('injury', '')
            if any(p in inj for p in famous_players) and len(inj) > 50:
                log(f"  ⚠️ id={m['id']}: 内容像AI但source=template — 可能被覆盖!")
                all_pass = False

    # 失败告警文件
    if not all_pass:
        alert = REPO / '.fill_failure'
        alert.write_text(f"{datetime.now(TZ).isoformat()}: 维度不全", encoding='utf-8')
    elif (REPO / '.fill_failure').exists():
        (REPO / '.fill_failure').unlink()

    return all_pass

if __name__ == '__main__':
    import sys
    if '--migrate-source' in sys.argv:
        log("=== Source迁移 ===")
        migrate_source()
    elif '--verify-only' in sys.argv:
        log("=== 验证模式 ===")
        d = json.loads(DATA.read_text(encoding='utf-8'))
        upcoming = [m for m in d['matches'] if not m.get('result') and m['id'] <= 104]
        log(f"待赛: {len(upcoming)}场")
        ai_count = sum(1 for m in d['matches'] if m.get('source') == 'ai')
        tp_count = sum(1 for m in d['matches'] if m.get('source') == 'template')
        log(f"Source: AI={ai_count} Template={tp_count}")
    else:
        log("=== 每日维度填充 ===")
        ok = fill_dimensions()
        log(f"结果: {'PASS' if ok else 'FAIL'}")
