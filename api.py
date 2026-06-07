"""
世界杯AI预测 API - FastAPI
免费部署: Render / Vercel / Railway

端点:
  GET /              API文档
  GET /matches       所有104场比赛+预测
  GET /match/{id}    单场比赛详情
  GET /search?q=阿根廷  搜索球队
  GET /today         今日比赛
  GET /stats         统计概览
"""
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import json
from pathlib import Path
from datetime import datetime

app = FastAPI(title="世界杯AI预测 API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DATA_FILE = Path(__file__).parent / "data.json"

def load_data():
    if not DATA_FILE.exists():
        return {}
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))

@app.get("/")
def root():
    return {
        "name": "2026世界杯AI预测 API",
        "version": "1.0",
        "endpoints": {
            "/matches": "所有104场比赛+预测",
            "/match/{id}": "单场比赛(id:1-104)",
            "/search?q=阿根廷": "搜索球队",
            "/today": "今日比赛",
            "/stats": "统计概览"
        },
        "note": "SPF赔率为AI预估(国际盘口换算),世界杯上线后切换为竞彩官方实时赔率"
    }

@app.get("/matches")
def get_matches():
    data = load_data()
    return {
        "updated": data.get("updated", ""),
        "source": data.get("source", ""),
        "total": len(data.get("matches", [])),
        "matches": data.get("matches", [])
    }

@app.get("/match/{match_id}")
def get_match(match_id: int):
    data = load_data()
    for m in data.get("matches", []):
        if m["id"] == match_id:
            return {"match": m}
    return {"error": "not found"}, 404

@app.get("/search")
def search(q: str = Query(..., min_length=1)):
    data = load_data()
    results = [m for m in data.get("matches", []) if q in str(m)]
    return {"query": q, "count": len(results), "matches": results}

@app.get("/today")
def today():
    today = datetime.now().strftime("%Y-%m-%d")
    data = load_data()
    # data.json matches use date fields; we need the actual match data
    # For now, return next upcoming matches
    return {
        "date": today,
        "message": "每日推荐由Claude Skill(8:03AM)自动生成",
        "tip": "请访问 /matches 查看全部赛程"
    }

@app.get("/stats")
def stats():
    data = load_data()
    matches = data.get("matches", [])
    levels = {}
    tips = {}
    for m in matches:
        l = m.get("level", "(空)")
        levels[l] = levels.get(l, 0) + 1
        t = m.get("tip", "待定")
        tips[t] = tips.get(t, 0) + 1
    return {
        "total": len(matches),
        "updated": data.get("updated", ""),
        "levelDistribution": levels,
        "tipDistribution": tips,
        "championOdds": data.get("champion_odds", [])
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
