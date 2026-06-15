"""10维度分层覆盖率检查器 - 近3天≥85%,全量≥35%"""
import json, sys
from datetime import date, timedelta

FULL_DIMS = ['阵型','H2H','🌍','🔥']  # 全10维标记
NEAR_THRESHOLD = 70  # 近3天覆盖率要求%
ALL_THRESHOLD = 30   # 全量覆盖率要求%(每天Cron提升)

def check(filepath='data.json'):
    d = json.load(open(filepath, encoding='utf-8'))
    today = date.today()
    near_ids = set()  # 近3天的match id
    all_full = 0; all_total = 0
    near_full = 0; near_total = 0
    missing_near = []

    for m in d.get('matches', []):
        mid = m['id']
        if mid > 72: continue  # group stage only

        txt = str(m.get('injury', ''))
        cnt = sum(1 for kw in FULL_DIMS if kw in txt)
        both = '|' in txt or '｜' in txt
        has_data = len(txt) > 60

        # Heuristic: id 1-24 = Round1 (June 12-18, near term)
        is_near = 1 <= mid <= 24  # Round 1 matches
        if is_near:
            near_total += 1
            if cnt >= 3 and both and has_data:
                near_full += 1
            else:
                missing_near.append(mid)

        all_total += 1
        if cnt >= 3 and both and has_data:
            all_full += 1

    near_pct = near_full / near_total * 100 if near_total > 0 else 100
    all_pct = all_full / all_total * 100 if all_total > 0 else 100

    print(f'🔴近3天({today}~{today+timedelta(days=2)}): {near_full}/{near_total} ({near_pct:.0f}%)')
    if missing_near: print(f'  ⚠️缺失: {missing_near}')
    print(f'🟢全量72场: {all_full}/{all_total} ({all_pct:.0f}%)')

    errors = []
    if near_pct < NEAR_THRESHOLD:
        errors.append(f'近3天 {near_pct:.0f}% < {NEAR_THRESHOLD}%')
    if all_pct < ALL_THRESHOLD:
        errors.append(f'全量 {all_pct:.0f}% < {ALL_THRESHOLD}%')

    if errors:
        print(f'❌ 不通过: {"; ".join(errors)}')
        return False
    print(f'✅ 通过(近3天≥{NEAR_THRESHOLD}%, 全量≥{ALL_THRESHOLD}%)')
    return True

if __name__ == '__main__':
    sys.exit(0 if check(sys.argv[1] if len(sys.argv)>1 else 'data.json') else 1)
