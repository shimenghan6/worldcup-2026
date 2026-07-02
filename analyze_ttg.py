"""TTG大小球AI分析: 赔率波动 + 11维度 → AI综合判断"""
import json, re
from pathlib import Path

REPO = Path(__file__).parent
DATA = REPO / 'data.json'
AI_PREDS = REPO / 'ai_predictions.json'
TTG_HIST = REPO / 'ttg_history.json'

def validate(match_id):
    """输入校验: 只对AI匹配+未完赛+injury长度>100的比赛运行"""
    d = json.loads(DATA.read_text(encoding='utf-8'))
    m = d['matches'][match_id - 1]
    if m.get('result'): return False, 'finished'
    if m.get('source') != 'ai': return False, 'not AI'
    if len(m.get('injury','')) < 100: return False, 'injury too short'
    return True, 'OK'

def analyze(match_id):
    """综合分析单场比赛的大小球
    返回: {verdict, expected_goals, market_exp, trend, dimension_bonus, confidence}"""
    ok, reason = validate(match_id)
    if not ok: return {'verdict': 'N/A', 'reason': reason}

    d = json.loads(DATA.read_text(encoding='utf-8'))
    ai = json.loads(AI_PREDS.read_text(encoding='utf-8'))
    hist = json.loads(TTG_HIST.read_text(encoding='utf-8')) if TTG_HIST.exists() else {}

    m = d['matches'][match_id - 1]
    mid = str(match_id)
    inj = m.get('injury', '')

    # 1. TTG当前期望
    ttg_data = ai.get(mid, {}).get('ttg', {})
    current_exp = ttg_data.get('expected', 2.5)

    # 2. 赔率波动分析
    trend = 'stable'
    first_exp = current_exp
    if mid in hist:
        snapshots = sorted(hist[mid].items())
        if len(snapshots) >= 2:
            first_exp = snapshots[0][1].get('expected', current_exp)
            last_exp = snapshots[-1][1].get('expected', current_exp)
            diff = last_exp - first_exp
            if diff > 0.3: trend = 'up'
            elif diff < -0.3: trend = 'down'

    # 3. 11维度加成
    bonus = 0
    reasons = []

    # D1: 伤病
    secs = inj.split('|') if '|' in inj else [inj, '']
    home_out = len(re.findall(r'❌', secs[0])) if len(secs) > 0 else 0
    away_out = len(re.findall(r'❌', secs[1])) if len(secs) > 1 else 0
    if home_out + away_out >= 2:
        bonus -= 0.5
        reasons.append(f'伤病-{home_out+away_out}核心缺阵(-0.5球)')

    # D2: 阵型
    h_fm = re.search(r'(\d)-(\d)-(\d)', secs[0]) if len(secs) > 0 else None
    a_fm = re.search(r'(\d)-(\d)-(\d)', secs[1]) if len(secs) > 1 else None
    if h_fm:
        if int(h_fm.group(1)) >= 5: bonus -= 0.3; reasons.append('主队5后卫(-0.3)')
        if int(h_fm.group(3)) >= 3: bonus += 0.3; reasons.append('主队3前锋(+0.3)')
    if a_fm:
        if int(a_fm.group(1)) >= 5: bonus -= 0.3; reasons.append('客队5后卫(-0.3)')
        if int(a_fm.group(3)) >= 3: bonus += 0.3; reasons.append('客队3前锋(+0.3)')

    # D5: 状态(高进球)
    h_form_gf = re.search(r'进(\d+)失', secs[0]) if len(secs) > 0 else None
    a_form_gf = re.search(r'进(\d+)失', secs[1]) if len(secs) > 1 else None
    if h_form_gf and int(h_form_gf.group(1)) >= 6: bonus += 0.3; reasons.append('主队高进球(+0.3)')
    if a_form_gf and int(a_form_gf.group(1)) >= 6: bonus += 0.3; reasons.append('客队高进球(+0.3)')

    # D4: 外界
    if '高原' in inj or '2240m' in inj: bonus += 0.2; reasons.append('高原(+0.2)')

    # D3: 矛盾
    if '德比' in inj or '复仇' in inj: bonus += 0.2; reasons.append('德比/复仇(+0.2)')

    # 综合
    adjusted = current_exp + bonus

    if adjusted >= 2.8:
        verdict = '大球'; conf = '高' if adjusted >= 3.2 else ('中' if adjusted >= 2.8 else '低')
    elif adjusted < 2.0:
        verdict = '小球'; conf = '高' if adjusted < 1.5 else ('中' if adjusted < 2.0 else '低')
    else:
        verdict = '均衡'; conf = '中' if abs(adjusted - 2.5) < 0.3 else '低'

    return {
        'verdict': verdict,
        'expected_goals': round(adjusted, 1),
        'market_exp': current_exp,
        'opening_exp': round(first_exp, 1),
        'trend': trend,
        'dimension_bonus': round(bonus, 2),
        'confidence': conf,
        'reasons': reasons[:3]
    }

def update_all():
    """所有待赛AI匹配运行TTG分析 → ai_predictions.json"""
    d = json.loads(DATA.read_text(encoding='utf-8'))
    ai = json.loads(AI_PREDS.read_text(encoding='utf-8'))
    count = 0
    for m in d['matches']:
        if m.get('result') or m['id'] > 104: continue
        if m.get('source') != 'ai': continue
        mid = str(m['id'])
        result = analyze(m['id'])
        if result.get('verdict') == 'N/A': continue
        if mid not in ai: ai[mid] = {}
        ai[mid]['ttg'] = result
        count += 1
        print(f'id={mid} {m["home"]}v{m["away"]}: {result["verdict"]} exp={result["expected_goals"]} trend={result["trend"]} conf={result["confidence"]}')
    AI_PREDS.write_text(json.dumps(ai, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\nUpdated {count} matches in ai_predictions.json')
    return count

if __name__ == '__main__':
    update_all()
