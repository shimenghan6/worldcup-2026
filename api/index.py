from flask import Flask, jsonify, request
import json, requests, time
from pathlib import Path

app = Flask(__name__)
DATA_URL = "https://raw.githubusercontent.com/shimenghan6/worldcup-2026/main/data.json"
KEYS_URL = "https://raw.githubusercontent.com/shimenghan6/worldcup-2026/main/api_keys.json"
LOCAL = Path(__file__).parent.parent
CACHE = {"data": None, "time": 0, "keys": None, "keys_time": 0}

def load_json(url, cache_key, ttl=120):
    now = time.time()
    if CACHE[cache_key] and (now - CACHE[cache_key+"_time"]) < ttl:
        return CACHE[cache_key]
    try:
        fname = "data.json" if "data" in cache_key else "api_keys.json"
        local_file = LOCAL / fname
        if local_file.exists():
            CACHE[cache_key] = json.loads(local_file.read_text(encoding="utf-8"))
        else:
            resp = requests.get(url, timeout=5)
            if resp.ok: CACHE[cache_key] = resp.json()
        CACHE[cache_key+"_time"] = now
    except:
        if CACHE[cache_key] is None: return {}
    return CACHE[cache_key] or {}

def check_key():
    key = request.args.get("key", "") or request.headers.get("X-API-Key", "")
    if not key: return None, "missing"
    keys_data = load_json(KEYS_URL, "keys", 300)
    keys = keys_data.get("keys", {})
    if key not in keys: return None, "invalid"
    return keys[key], "ok"

def require_key(f):
    def wrapper(*a, **kw):
        info, status = check_key()
        if status == "missing":
            return jsonify({"error":"需要API Key","get_key":"/pricing","try":"?key=wc2026-demo-free"}), 401
        if status == "invalid":
            return jsonify({"error":"无效的API Key","get_key":"/pricing"}), 403
        return f(*a, **kw)
    wrapper.__name__ = f.__name__
    return wrapper

@app.route("/")
def home():
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>世界杯AI预测 API</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;background:#0a0e27;color:#e0e0e0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.card{background:#111640;border-radius:20px;padding:40px;max-width:700px;width:100%;border:1px solid #1e2358}
h1{font-size:2em;text-align:center;margin-bottom:8px}
h1 span{background:linear-gradient(135deg,#f5c542,#e67e22);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.sub{text-align:center;color:#8890b5;margin-bottom:32px}
.plans{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:24px}
.plan{background:rgba(255,255,255,0.03);border:1px solid #1e2358;border-radius:14px;padding:24px;text-align:center;transition:.2s}
.plan:hover{border-color:#00d4aa;transform:translateY(-2px)}
.plan h3{font-size:1.1em;margin-bottom:8px}
.plan .price{font-size:2em;font-weight:900;color:#00d4aa;margin:12px 0}
.plan .price small{font-size:.4em;color:#8890b5}
.plan .limit{color:#8890b5;font-size:.85em;margin-bottom:12px}
.plan .btn{display:inline-block;padding:8px 20px;border-radius:20px;background:#00d4aa;color:#000;font-weight:700;text-decoration:none;font-size:.9em}
.plan.free .btn{background:#1e2358;color:#8890b5}
.demo{text-align:center;padding:16px;background:rgba(0,212,170,0.06);border-radius:12px;margin:16px 0}
.demo code{background:rgba(0,0,0,.3);padding:3px 8px;border-radius:4px;color:#00d4aa;font-size:.9em}
.endpoints{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:16px 0}
.endpoints .ep{background:rgba(0,0,0,.2);padding:8px 12px;border-radius:8px;font-size:.85em}
.endpoints .ep .method{color:#f5c542;font-weight:700;margin-right:6px}
.endpoints .ep .path{color:#e0e0e0}
footer{text-align:center;color:#8890b5;font-size:.8em;margin-top:24px}
@media(max-width:500px){.card{padding:24px}.plans{grid-template-columns:1fr}.endpoints{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="card">
<h1>🏆 <span>世界杯AI预测</span> API</h1>
<div class="sub">104场比赛 · 每日AI分析 · 竞彩官方赔率</div>

<div class="plans">
<div class="plan free"><h3>🆓 免费</h3><div class="price">¥0<small>/月</small></div><div class="limit">100次/天</div><a class="btn" href="/stats?key=wc2026-demo-free">试用 →</a></div>
<div class="plan"><h3>💎 PRO</h3><div class="price">¥9.9<small>/月</small></div><div class="limit">1000次/天</div><a class="btn" href="/pricing">购买 →</a></div>
<div class="plan"><h3>🚀 企业</h3><div class="price">¥99<small>/月</small></div><div class="limit">无限</div><a class="btn" href="/pricing">联系 →</a></div>
</div>

<div class="demo">🔑 免费试用Key：<code>wc2026-demo-free</code></div>

<div class="endpoints">
<div class="ep"><span class="method">GET</span><span class="path">/stats</span></div>
<div class="ep"><span class="method">GET</span><span class="path">/matches</span></div>
<div class="ep"><span class="method">GET</span><span class="path">/match/:id</span></div>
<div class="ep"><span class="method">GET</span><span class="path">/search?q=xx</span></div>
</div>

<footer>🤖 AI分析 · 数据每日更新 · 扫码付款获取PRO Key</footer>
</div>
</body>
</html>"""

@app.route("/pricing")
def pricing_html():
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>定价 · 世界杯AI预测 API</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;background:#0a0e27;color:#e0e0e0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.card{background:#111640;border-radius:20px;padding:40px;max-width:800px;width:100%;border:1px solid #1e2358}
h1{text-align:center;margin-bottom:24px}
.plans{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:20px;margin-bottom:32px}
.plan{background:rgba(255,255,255,0.03);border:1px solid #1e2358;border-radius:16px;padding:28px;text-align:center}
.plan.pro{border-color:#00d4aa;background:rgba(0,212,170,0.05)}
.plan h3{font-size:1.2em;margin-bottom:4px}
.plan .price{font-size:2.4em;font-weight:900;color:#00d4aa;margin:16px 0}
.plan .price small{font-size:.35em;color:#8890b5}
.plan .feat{color:#8890b5;font-size:.9em;margin:8px 0}
.qr-section{text-align:center;padding:24px;background:rgba(245,197,66,0.05);border-radius:16px;border:1px solid rgba(245,197,66,0.15)}
.qr-section img{width:200px;height:200px;border-radius:12px;margin:16px auto;display:block}
.qr-section h3{color:#f5c542;margin-bottom:8px}
.qr-section p{color:#8890b5;font-size:.9em;margin:4px 0}
.back{text-align:center;margin-top:24px}
.back a{color:#00d4aa;text-decoration:none;font-size:.9em}
@media(max-width:500px){.card{padding:24px}.plans{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="card">
<h1>💰 选择套餐</h1>
<div class="plans">
<div class="plan"><h3>🆓 免费试用</h3><div class="price">¥0<small>/月</small></div><div class="feat">100次/天</div><div class="feat">全部端点</div><div class="feat">Key: wc2026-demo-free</div></div>
<div class="plan pro"><h3>💎 PRO</h3><div class="price">¥9.9<small>/月</small></div><div class="feat">1000次/天</div><div class="feat">全部端点</div><div class="feat">优先支持</div></div>
<div class="plan"><h3>🚀 企业</h3><div class="price">¥99<small>/月</small></div><div class="feat">无限调用</div><div class="feat">全部端点</div><div class="feat">定制方案</div></div>
</div>
<div class="qr-section">
<h3>📱 扫码付款 (PRO · ¥9.9/月)</h3>
<img src="https://raw.githubusercontent.com/shimenghan6/worldcup-2026/main/pay_qr.jpg" alt="收款码" onerror="this.nextSibling.style.display='block';this.style.display='none'">
<span style="display:none;color:#8890b5">收款码: pay_qr.jpg</span>
<p>微信扫码 → 付款 → 截图发给客服 → 获取PRO Key</p>
</div>
<div class="back"><a href="/">← 返回API首页</a></div>
</div>
</body>
</html>"""

@app.route("/pricing.json")
def pricing_json():
    return jsonify({
        "plans": {
            "free": {"price":"免费","limit":"100次/天","key":"wc2026-demo-free","desc":"试用演示"},
            "pro": {"price":"¥9.9/月","limit":"1000次/天","desc":"个人开发者"},
            "enterprise": {"price":"¥99/月","limit":"无限","desc":"商业使用"}
        },
        "payment_qr":"https://raw.githubusercontent.com/shimenghan6/worldcup-2026/main/pay_qr.jpg"
    })

@app.route("/matches")
@require_key
def matches():
    d = load_json(DATA_URL, "data", 60)
    return jsonify({"total":len(d.get("matches",[])),"matches":d.get("matches",[])})

@app.route("/match/<int:mid>")
@require_key
def match(mid):
    d = load_json(DATA_URL, "data", 60)
    m = next((m for m in d.get("matches",[]) if m["id"]==mid), None)
    return jsonify({"match":m}) if m else (jsonify({"error":"not found"}),404)

@app.route("/search")
@require_key
def search():
    q = request.args.get("q","")
    d = load_json(DATA_URL, "data", 60)
    results = [m for m in d.get("matches",[]) if q in str(m)]
    return jsonify({"query":q,"count":len(results),"matches":results})

@app.route("/stats")
@require_key
def stats():
    d = load_json(DATA_URL, "data", 60)
    matches = d.get("matches",[])
    levels={}; tips={}
    for m in matches:
        l=m.get("level","(空)"); levels[l]=levels.get(l,0)+1
        t=m.get("tip","待定"); tips[t]=tips.get(t,0)+1
    return jsonify({"total":len(matches),"levelDistribution":levels,"tipDistribution":tips,"championOdds":d.get("champion_odds",[])})
