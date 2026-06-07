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
        # Try local file first (faster, works offline)
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
    if not key:
        return None, "missing"
    keys_data = load_json(KEYS_URL, "keys", 300)
    keys = keys_data.get("keys", {})
    if key not in keys:
        return None, "invalid"
    return keys[key], "ok"

@app.route("/")
def root():
    return jsonify({
        "name": "2026世界杯AI预测 API",
        "version": "1.0",
        "auth": "?key=YOUR_API_KEY",
        "endpoints": ["/matches", "/match/<id>", "/search?q=xx", "/stats", "/pricing"]
    })

@app.route("/pricing")
def pricing():
    return jsonify({
        "plans": {
            "free": {"price": "免费", "limit": "100次/天", "key": "wc2026-demo-free"},
            "pro": {"price": "¥9.9/月", "limit": "1000次/天", "how": "微信扫码付款后发Key"},
            "enterprise": {"price": "¥99/月", "limit": "无限", "how": "联系定制"}
        },
        "payment": "微信: [你的收款码]",
        "contact": "付款后发送截图获取API Key"
    })

def require_key(f):
    def wrapper(*a, **kw):
        info, status = check_key()
        if status == "missing":
            return jsonify({"error": "需要API Key", "get_key": "/pricing", "try": "?key=wc2026-demo-free"}), 401
        if status == "invalid":
            return jsonify({"error": "无效的API Key", "get_key": "/pricing"}), 403
        return f(*a, **kw)
    wrapper.__name__ = f.__name__
    return wrapper

@app.route("/matches")
@require_key
def matches():
    d = load_json(DATA_URL, "data", 60)
    return jsonify({"total": len(d.get("matches", [])), "matches": d.get("matches", [])})

@app.route("/match/<int:mid>")
@require_key
def match(mid):
    d = load_json(DATA_URL, "data", 60)
    m = next((m for m in d.get("matches", []) if m["id"] == mid), None)
    return jsonify({"match": m}) if m else (jsonify({"error": "not found"}), 404)

@app.route("/search")
@require_key
def search():
    q = request.args.get("q", "")
    d = load_json(DATA_URL, "data", 60)
    results = [m for m in d.get("matches", []) if q in str(m)]
    return jsonify({"query": q, "count": len(results), "matches": results})

@app.route("/stats")
@require_key
def stats():
    d = load_json(DATA_URL, "data", 60)
    matches = d.get("matches", [])
    levels = {}; tips = {}
    for m in matches:
        l = m.get("level", "(空)"); levels[l] = levels.get(l, 0) + 1
        t = m.get("tip", "待定"); tips[t] = tips.get(t, 0) + 1
    return jsonify({"total": len(matches), "levelDistribution": levels, "tipDistribution": tips, "championOdds": d.get("champion_odds", [])})
