from flask import Flask, jsonify, request
import json
from pathlib import Path

app = Flask(__name__)
DATA_FILE = Path(__file__).parent.parent / "data.json"

def load_data():
    if not DATA_FILE.exists(): return {}
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))

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
