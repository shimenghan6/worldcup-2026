from flask import Flask, jsonify, request
import json, requests
from pathlib import Path

app = Flask(__name__)
# 实时从GitHub读取data.json(无需重新部署)
DATA_URL = "https://raw.githubusercontent.com/shimenghan6/worldcup-2026/main/data.json"
LOCAL_FILE = Path(__file__).parent.parent / "data.json"
CACHE = {"data": None, "time": 0}

def load_data():
    import time
    # 60秒缓存,避免每次请求都打GitHub
    now = time.time()
    if CACHE["data"] and (now - CACHE["time"]) < 60:
        return CACHE["data"]
    try:
        resp = requests.get(DATA_URL, timeout=5)
        if resp.ok:
            CACHE["data"] = resp.json()
            CACHE["time"] = now
            return CACHE["data"]
    except:
        pass
    # Fallback to local file
    if LOCAL_FILE.exists():
        return json.loads(LOCAL_FILE.read_text(encoding="utf-8"))
    return {}

@app.route("/")
def root():
    return jsonify({"name":"2026世界杯AI预测 API","endpoints":["/matches","/match/<id>","/search?q=xx","/stats"]})

@app.route("/matches")
def matches():
    d = load_data()
    return jsonify({"total":len(d.get("matches",[])),"matches":d.get("matches",[])})

@app.route("/match/<int:mid>")
def match(mid):
    d = load_data()
    m = next((m for m in d.get("matches",[]) if m["id"]==mid), None)
    return jsonify({"match":m}) if m else (jsonify({"error":"not found"}),404)

@app.route("/search")
def search():
    q = request.args.get("q","")
    d = load_data()
    results = [m for m in d.get("matches",[]) if q in str(m)]
    return jsonify({"query":q,"count":len(results),"matches":results})

@app.route("/stats")
def stats():
    d = load_data()
    matches = d.get("matches",[])
    levels={}; tips={}
    for m in matches:
        l=m.get("level","(空)"); levels[l]=levels.get(l,0)+1
        t=m.get("tip","待定"); tips[t]=tips.get(t,0)+1
    return jsonify({"total":len(matches),"levelDistribution":levels,"tipDistribution":tips,"championOdds":d.get("champion_odds",[])})
