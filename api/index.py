"""
世界杯AI预测 API - Vercel Serverless
免费部署: vercel.com (无需信用卡)
"""
from http.server import BaseHTTPRequestHandler
import json
from pathlib import Path
from datetime import datetime

DATA_FILE = Path(__file__).parent.parent / "data.json"

def load_data():
    if not DATA_FILE.exists():
        return {}
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = load_data()
        path = self.path.rstrip("/")

        # CORS
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        try:
            if path == "" or path == "/":
                result = {"name": "2026世界杯AI预测 API", "endpoints": ["/matches", "/match/{id}", "/search?q=xx", "/stats"]}
            elif path == "/matches":
                result = {"total": len(data.get("matches", [])), "matches": data.get("matches", [])}
            elif path == "/stats":
                matches = data.get("matches", [])
                levels = {}; tips = {}
                for m in matches:
                    l = m.get("level", "(空)"); levels[l] = levels.get(l, 0) + 1
                    t = m.get("tip", "待定"); tips[t] = tips.get(t, 0) + 1
                result = {"total": len(matches), "levelDistribution": levels, "tipDistribution": tips, "championOdds": data.get("champion_odds", [])}
            elif path.startswith("/match/"):
                mid = int(path.split("/")[-1])
                m = next((m for m in data.get("matches", []) if m["id"] == mid), None)
                result = {"match": m} if m else {"error": "not found"}
            elif path.startswith("/search"):
                q = path.split("q=")[-1] if "q=" in path else ""
                results = [m for m in data.get("matches", []) if q in str(m)]
                result = {"query": q, "count": len(results), "matches": results}
            else:
                result = {"error": "unknown endpoint", "try": ["/matches", "/match/1", "/search?q=阿根廷", "/stats"]}
        except Exception as e:
            result = {"error": str(e)}

        self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        pass  # suppress logs
