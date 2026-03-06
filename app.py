#!/usr/bin/env python3
"""
⛽ Spritpreis-Tracker v3 – Cloud Deployment Version
Datenquelle: Tankerkönig API (CC BY 4.0)
"""

import os, threading, webbrowser, time, sys, json
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
import requests
from flask import Flask, jsonify, request, Response

# ── Konfiguration ────────────────────────────────────────
TANKERKOENIG_API_KEY = os.environ.get("TANKERKOENIG_API_KEY", "")
PORT = int(os.environ.get("PORT", 7331))
IS_LOCAL = not os.environ.get("RAILWAY_ENVIRONMENT") and not os.environ.get("RENDER")

# Persistenter Speicher: /data im Cloud, ~/.spritpreis_tracker lokal
if IS_LOCAL:
    DATA_DIR = Path.home() / ".spritpreis_tracker"
else:
    DATA_DIR = Path("/tmp/spritpreis_tracker")

DATA_DIR.mkdir(parents=True, exist_ok=True)
FAVORITES_FILE = DATA_DIR / "favorites.json"
HISTORY_FILE   = DATA_DIR / "history.json"

def load_json(p, default):
    try:
        if p.exists(): return json.loads(p.read_text(encoding="utf-8"))
    except Exception: pass
    return default

def save_json(p, data):
    try:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception: pass

def update_history(stations_list):
    history = load_json(HISTORY_FILE, {})
    now = datetime.now().isoformat()
    for s in stations_list:
        sid = s.get("id")
        if not sid: continue
        entry = {"ts": now, "e5": s.get("e5"), "e10": s.get("e10"), "diesel": s.get("diesel")}
        if sid not in history:
            history[sid] = {"name": s.get("brand") or s.get("name", ""), "prices": []}
        prices = history[sid]["prices"]
        if prices:
            last = prices[-1]
            same = (last.get("e5") == entry["e5"] and last.get("e10") == entry["e10"]
                    and last.get("diesel") == entry["diesel"])
            try:
                mins_ago = (datetime.now() - datetime.fromisoformat(last["ts"])).total_seconds() / 60
            except Exception:
                mins_ago = 999
            if same and mins_ago < 30:
                continue
        prices.append(entry)
        history[sid]["prices"] = prices[-60:]
    save_json(HISTORY_FILE, history)

# ── Flask ────────────────────────────────────────────────
app = Flask(__name__)

@app.route("/")
def index():
    return Response(HTML, mimetype="text/html")

@app.route("/api/geocode")
def geocode():
    plz = request.args.get("plz", "").strip()
    q   = request.args.get("q", "").strip()
    if plz:
        if not plz.isdigit() or len(plz) != 5:
            return jsonify({"error": "Ungültige PLZ (5 Ziffern)"}), 400
        url = f"https://nominatim.openstreetmap.org/search?postalcode={plz}&country=DE&format=json"
    elif q:
        url = f"https://nominatim.openstreetmap.org/search?q={quote(q, safe='')}&format=json&limit=1&addressdetails=1"
    else:
        return jsonify({"error": "PLZ oder Adresse angeben"}), 400
    try:
        r = requests.get(url, headers={"User-Agent": "SpritpreisTracker/3.0"}, timeout=8)
        r.raise_for_status()
        data = r.json()
        if not data:
            return jsonify({"error": "Adresse nicht gefunden"}), 404
        item = data[0]
        return jsonify({"lat": float(item["lat"]), "lon": float(item["lon"]), "display_name": item.get("display_name", "")})
    except Exception as e:
        return jsonify({"error": f"Geocoding fehlgeschlagen: {e}"}), 500

@app.route("/api/stations")
def stations():
    if not TANKERKOENIG_API_KEY:
        return jsonify({"error": "TANKERKOENIG_API_KEY nicht gesetzt"}), 500
    lat = request.args.get("lat")
    lng = request.args.get("lng")
    rad = request.args.get("rad", "10")
    if not lat or not lng:
        return jsonify({"error": "lat/lng erforderlich"}), 400
    radius = min(max(float(rad), 1), 25)
    try:
        url = (f"https://creativecommons.tankerkoenig.de/json/list.php"
               f"?lat={lat}&lng={lng}&rad={radius}&type=all&apikey={TANKERKOENIG_API_KEY}")
        r = requests.get(url, headers={"User-Agent": "SpritpreisTracker/3.0"}, timeout=10)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            return jsonify({"error": data.get("message", "Tankerkönig API Fehler")}), 502
        sl = data.get("stations", [])
        update_history(sl)
        return jsonify({"stations": sl, "source": "tankerkoenig", "timestamp": datetime.utcnow().isoformat() + "Z"})
    except Exception as e:
        return jsonify({"error": f"Abfrage fehlgeschlagen: {e}"}), 500

@app.route("/api/history/<sid>")
def get_history(sid):
    h = load_json(HISTORY_FILE, {})
    return jsonify(h.get(sid, {"prices": []}))

@app.route("/api/favorites", methods=["GET"])
def get_favorites():
    return jsonify(load_json(FAVORITES_FILE, []))

@app.route("/api/favorites/<sid>", methods=["POST", "DELETE"])
def toggle_fav(sid):
    favs = load_json(FAVORITES_FILE, [])
    if request.method == "POST":
        if sid not in favs: favs.append(sid)
    else:
        favs = [f for f in favs if f != sid]
    save_json(FAVORITES_FILE, favs)
    return jsonify(favs)

@app.route("/health")
def health():
    return jsonify({"status": "ok", "api_key_set": bool(TANKERKOENIG_API_KEY)})

# ── HTML ─────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no"/>
<title>⛽ Spritpreis-Tracker</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=Barlow:wght@300;400;500;600&display=swap" rel="stylesheet"/>
<style>
:root{
  --amber:#f5a623;--amber-glow:rgba(245,166,35,.18);--amber-border:rgba(245,166,35,.35);
  --green:#22c55e;--red:#ef4444;--blue:#3b82f6;
  --bg:#111214;--bg2:#18191d;--bg3:#1f2025;--bg4:#26272d;--bg5:#2d2e35;
  --border:rgba(255,255,255,.07);--text:#e8e9ec;--dim:#7c7f8a;--muted:#4b4d55;--r:8px;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Barlow',sans-serif;min-height:100vh;overflow-x:hidden}
header{background:var(--bg2);border-bottom:1px solid var(--border);padding:0 18px;display:flex;align-items:center;justify-content:space-between;height:52px;position:sticky;top:0;z-index:1000}
.logo{display:flex;align-items:center;gap:9px}
.logo-icon{width:30px;height:30px;background:var(--amber);border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0}
.logo-text{font-family:'Barlow Condensed',sans-serif;font-size:19px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--text)}
.logo-text span{color:var(--amber)}
.header-meta{display:flex;align-items:center;gap:10px}
#source-badge{font-family:'Barlow Condensed',sans-serif;font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:3px 8px;border-radius:4px;background:rgba(34,197,94,.1);color:var(--green);border:1px solid rgba(34,197,94,.25)}
#refresh-badge{display:none;align-items:center;gap:5px;background:var(--bg3);border:1px solid var(--border);border-radius:16px;padding:3px 10px;font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--dim)}
#refresh-badge.active{display:flex}
.pulse{width:6px;height:6px;border-radius:50%;background:var(--amber);animation:pulse 1.5s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.7)}}
.search-panel{background:var(--bg2);border-bottom:1px solid var(--border);padding:14px 18px}
.search-mode-toggle{display:flex;margin-bottom:10px;background:var(--bg3);border:1px solid var(--border);border-radius:var(--r);overflow:hidden;width:fit-content}
.mode-btn{padding:6px 16px;border:none;background:transparent;color:var(--dim);font-family:'Barlow Condensed',sans-serif;font-size:13px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;cursor:pointer;transition:all .15s}
.mode-btn.active{background:var(--amber);color:var(--bg)}
.search-row{display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap}
.field-grp{display:flex;flex-direction:column;gap:4px}
.field-label{font-family:'Barlow Condensed',sans-serif;font-size:10px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--dim)}
.txt-input{background:var(--bg3);border:1px solid var(--border);border-radius:var(--r);color:var(--text);font-family:'IBM Plex Mono',monospace;font-size:15px;padding:8px 12px;outline:none;transition:border-color .2s,box-shadow .2s;min-width:0}
.txt-input:focus{border-color:var(--amber);box-shadow:0 0 0 3px var(--amber-glow)}
.txt-input.error{border-color:var(--red);box-shadow:0 0 0 3px rgba(239,68,68,.15)}
#plz-input{width:120px;font-size:16px}
#addr-input{width:260px;font-size:14px}
.radius-sel{background:var(--bg3);border:1px solid var(--border);border-radius:var(--r);color:var(--text);font-family:'Barlow',sans-serif;font-size:14px;padding:8px 30px 8px 12px;outline:none;cursor:pointer;appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='7' viewBox='0 0 10 7'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%237c7f8a' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 10px center;min-width:100px}
.radius-sel:focus{border-color:var(--amber)}
.fuel-toggle{display:flex;background:var(--bg3);border:1px solid var(--border);border-radius:var(--r);overflow:hidden}
.fuel-btn{padding:8px 14px;border:none;background:transparent;color:var(--dim);font-family:'Barlow Condensed',sans-serif;font-size:13px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;cursor:pointer;transition:all .15s}
.fuel-btn:not(:last-child){border-right:1px solid var(--border)}
.fuel-btn.active{background:var(--amber);color:var(--bg)}
.fuel-btn:not(.active):hover{background:var(--bg4);color:var(--text)}
.search-btn{background:var(--amber);color:var(--bg);border:none;border-radius:var(--r);padding:8px 20px;font-family:'Barlow Condensed',sans-serif;font-size:14px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;cursor:pointer;transition:background .15s,transform .1s;display:flex;align-items:center;gap:6px;white-space:nowrap}
.search-btn:hover:not(:disabled){background:#e8951e}
.search-btn:active:not(:disabled){transform:scale(.97)}
.search-btn:disabled{opacity:.5;cursor:not-allowed}
#status-bar{display:none;align-items:center;gap:8px;padding:7px 18px;background:var(--bg3);border-bottom:1px solid var(--border);font-size:12px;color:var(--dim);flex-wrap:wrap}
#status-bar.visible{display:flex}
#status-bar.err{color:var(--red)}
.main{display:flex;height:calc(100vh - 52px - 65px);overflow:hidden}
#map-container{flex:1;position:relative;min-height:0}
#map{width:100%;height:100%}
.map-loader{position:absolute;inset:0;background:rgba(17,18,20,.75);display:none;align-items:center;justify-content:center;z-index:800;backdrop-filter:blur(2px)}
.map-loader.on{display:flex}
.spinner{width:36px;height:36px;border:3px solid var(--border);border-top-color:var(--amber);border-radius:50%;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
#list-panel{width:340px;background:var(--bg2);border-left:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;flex-shrink:0}
.list-header{padding:10px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;flex-shrink:0;gap:8px}
.list-title{font-family:'Barlow Condensed',sans-serif;font-size:12px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--dim)}
#stn-count{font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--amber);background:var(--amber-glow);border:1px solid var(--amber-border);border-radius:10px;padding:1px 8px;display:none}
#station-list{flex:1;overflow-y:auto;scrollbar-width:thin;scrollbar-color:var(--bg5) transparent}
#station-list::-webkit-scrollbar{width:3px}
#station-list::-webkit-scrollbar-thumb{background:var(--bg5);border-radius:2px}
.placeholder{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:10px;padding:20px;text-align:center}
.placeholder .ico{font-size:36px;opacity:.35}
.placeholder p{font-size:13px;color:var(--dim);line-height:1.5}
.section-sep{display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--bg3);border-bottom:1px solid var(--border)}
.sep-label{font-family:'Barlow Condensed',sans-serif;font-size:10px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);white-space:nowrap}
.sep-line{flex:1;height:1px;background:var(--border)}
.stn-card{display:flex;align-items:flex-start;gap:10px;padding:10px 12px;border-bottom:1px solid var(--border);cursor:pointer;transition:background .1s;position:relative}
.stn-card:hover{background:var(--bg3)}
.stn-card.fav-card{background:rgba(245,166,35,.04)}
.stn-card.fav-card::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--amber)}
.stn-card.cheapest-card::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--green)}
.card-left{display:flex;flex-direction:column;align-items:center;gap:6px;flex-shrink:0;padding-top:1px}
.rank-num{font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:600;color:var(--muted);width:18px;text-align:right}
.fav-btn{background:none;border:none;cursor:pointer;padding:2px;font-size:16px;line-height:1;opacity:.6;transition:opacity .15s,transform .15s;color:var(--amber)}
.fav-btn:hover{opacity:1;transform:scale(1.2)}
.fav-btn.active{opacity:1}
.card-info{flex:1;min-width:0}
.card-brand{font-family:'Barlow Condensed',sans-serif;font-size:15px;font-weight:700;letter-spacing:.03em;text-transform:uppercase;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.2}
.card-addr{font-size:12px;color:var(--dim);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card-meta{display:flex;gap:6px;margin-top:5px;align-items:center;flex-wrap:wrap}
.dist-badge{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--dim)}
.open-badge{font-family:'Barlow Condensed',sans-serif;font-size:10px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;padding:1px 6px;border-radius:3px}
.open-badge.open{background:rgba(34,197,94,.12);color:var(--green);border:1px solid rgba(34,197,94,.25)}
.open-badge.closed{background:rgba(239,68,68,.1);color:var(--red);border:1px solid rgba(239,68,68,.2)}
.hist-btn{background:none;border:1px solid var(--border);border-radius:4px;cursor:pointer;padding:1px 6px;font-size:10px;color:var(--dim);transition:all .15s;font-family:'Barlow Condensed',sans-serif;letter-spacing:.04em;text-transform:uppercase;font-weight:600}
.hist-btn:hover{border-color:var(--amber);color:var(--amber)}
.card-price{text-align:right;flex-shrink:0}
.price-big{font-family:'IBM Plex Mono',monospace;font-size:19px;font-weight:600;color:var(--text);line-height:1}
.price-big.cheapest{color:var(--green)}
.price-big.fav-price{color:var(--amber)}
.price-big.na{font-size:10px;color:var(--muted);font-weight:400;margin-top:4px}
.price-sup{font-size:11px;vertical-align:super;font-weight:400}
.price-unit{display:block;font-family:'Barlow Condensed',sans-serif;font-size:9px;color:var(--muted);letter-spacing:.06em;text-transform:uppercase;margin-top:1px}
.crown{position:absolute;top:6px;right:6px;font-size:11px}
.leaflet-popup-content-wrapper{background:var(--bg2)!important;border:1px solid var(--amber-border)!important;border-radius:8px!important;box-shadow:0 8px 32px rgba(0,0,0,.55)!important;color:var(--text)!important;font-family:'Barlow',sans-serif!important;padding:0!important}
.leaflet-popup-tip{background:var(--bg2)!important}
.leaflet-popup-content{margin:0!important;width:230px!important}
.pu{padding:13px}
.pu-brand{font-family:'Barlow Condensed',sans-serif;font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--amber)}
.pu-addr{font-size:12px;color:var(--dim);margin:3px 0 10px;line-height:1.4}
.pu-prices{display:grid;grid-template-columns:repeat(3,1fr);gap:5px;border-top:1px solid var(--border);padding-top:9px}
.pu-pi{background:var(--bg3);border-radius:5px;padding:6px 4px;text-align:center}
.pu-lbl{font-family:'Barlow Condensed',sans-serif;font-size:9px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);display:block;margin-bottom:2px}
.pu-val{font-family:'IBM Plex Mono',monospace;font-size:13px;font-weight:600;color:var(--text)}
.pu-val.na{font-size:9px;color:var(--muted)}
.pu-foot{margin-top:8px;display:flex;align-items:center;justify-content:space-between}
#hist-modal{position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:2000;display:none;align-items:center;justify-content:center;backdrop-filter:blur(4px);padding:20px}
#hist-modal.on{display:flex}
.hist-box{background:var(--bg2);border:1px solid var(--amber-border);border-radius:12px;width:100%;max-width:520px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.6)}
.hist-head{padding:14px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.hist-title{font-family:'Barlow Condensed',sans-serif;font-size:15px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--text)}
.hist-close{background:none;border:none;cursor:pointer;color:var(--dim);font-size:22px;line-height:1;padding:0 2px;transition:color .15s}
.hist-close:hover{color:var(--text)}
.hist-body{padding:18px}
.hist-fuel-tabs{display:flex;gap:4px;margin-bottom:14px}
.hf-btn{padding:5px 12px;border:1px solid var(--border);border-radius:6px;background:transparent;color:var(--dim);font-family:'Barlow Condensed',sans-serif;font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;cursor:pointer;transition:all .15s}
.hf-btn.active{background:var(--amber);color:var(--bg);border-color:var(--amber)}
.hist-canvas-wrap{position:relative;height:160px;background:var(--bg3);border-radius:8px;overflow:hidden}
.hist-empty{display:flex;align-items:center;justify-content:center;height:160px;background:var(--bg3);border-radius:8px;color:var(--muted);font-size:13px;text-align:center;padding:16px}
.hist-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px}
.stat-box{background:var(--bg3);border-radius:6px;padding:10px;text-align:center}
.stat-label{font-family:'Barlow Condensed',sans-serif;font-size:10px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);margin-bottom:4px;display:block}
.stat-val{font-family:'IBM Plex Mono',monospace;font-size:15px;font-weight:600;color:var(--text)}
.stat-val.low{color:var(--green)}
.stat-val.high{color:var(--red)}
#toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%) translateY(70px);background:var(--bg4);border:1px solid var(--border);border-radius:8px;padding:9px 16px;font-size:13px;color:var(--text);z-index:9999;transition:transform .3s cubic-bezier(.34,1.56,.64,1);pointer-events:none;white-space:nowrap}
#toast.show{transform:translateX(-50%) translateY(0)}
#toast.ok{border-color:rgba(34,197,94,.3)}
#toast.err{border-color:rgba(239,68,68,.3);color:#fca5a5}
@media(max-width:768px){
  .main{flex-direction:column;height:auto;overflow:visible}
  #map-container{height:40vh;flex:none;touch-action:none}
  #list-panel{width:100%;border-left:none;border-top:1px solid var(--border);height:auto;min-height:50vh;overflow-y:auto}
  #station-list{height:auto;overflow-y:visible}
  #scroll-btn{display:none;position:fixed;bottom:20px;right:16px;z-index:900;background:var(--amber);color:var(--bg);border:none;border-radius:24px;padding:10px 16px;font-family:'Barlow Condensed',sans-serif;font-size:13px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;cursor:pointer;box-shadow:0 4px 16px rgba(0,0,0,.4);gap:6px;align-items:center}
  #scroll-btn.visible{display:flex}
  #addr-input{width:100%}
  .card-brand{font-size:13px}
  .price-big{font-size:15px}
  .price-sup{font-size:9px}
  .price-unit{font-size:8px}
  .stn-card{padding:8px 10px;gap:6px}
  .card-price{min-width:52px}
  .search-panel{padding:10px 12px}
  .search-row{gap:6px}
  .fuel-btn{padding:7px 10px;font-size:12px}
  .txt-input{font-size:14px}
}
.leaflet-tile-pane{filter:brightness(.82) saturate(.55)}
</style>
</head>
<body>
<header>
  <div class="logo">
    <div class="logo-icon">⛽</div>
    <div class="logo-text">Sprit<span>preis</span></div>
  </div>
  <div class="header-meta">
    <div id="source-badge">Tankerkönig API</div>
    <div id="refresh-badge">
      <div class="pulse"></div>
      <span>Refresh in <strong id="countdown">—</strong></span>
    </div>
  </div>
</header>
<div class="search-panel">
  <div class="search-mode-toggle">
    <button class="mode-btn active" onclick="setMode('plz')">PLZ</button>
    <button class="mode-btn" onclick="setMode('addr')">Adresse</button>
  </div>
  <div class="search-row">
    <div class="field-grp">
      <div class="field-label" id="search-label">Postleitzahl</div>
      <input type="text" id="plz-input" class="txt-input" placeholder="12345" maxlength="5" inputmode="numeric"/>
      <input type="text" id="addr-input" class="txt-input" placeholder="z.B. Rosenheimer Str. 1, München" style="display:none"/>
    </div>
    <div class="field-grp">
      <div class="field-label">Umkreis</div>
      <select id="radius-sel" class="radius-sel">
        <option value="2">2 km</option>
        <option value="5">5 km</option>
        <option value="10" selected>10 km</option>
        <option value="20">20 km</option>
      </select>
    </div>
    <div class="field-grp">
      <div class="field-label">Kraftstoff</div>
      <div class="fuel-toggle">
        <button class="fuel-btn" data-fuel="e5">E5</button>
        <button class="fuel-btn active" data-fuel="e10">E10</button>
        <button class="fuel-btn" data-fuel="diesel">Diesel</button>
      </div>
    </div>
    <button id="search-btn" class="search-btn" onclick="doSearch()">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      Suchen
    </button>
  </div>
</div>
<div id="status-bar">
  <svg id="status-ico" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"></svg>
  <span id="status-txt"></span>
</div>
<div class="main">
  <div id="map-container">
    <div id="map"></div>
    <div class="map-loader" id="map-loader"><div class="spinner"></div></div>
  </div>
  <div id="list-panel">
    <div class="list-header">
      <span class="list-title">Tankstellen</span>
      <span id="stn-count"></span>
    </div>
    <div id="station-list">
      <div class="placeholder"><div class="ico">🗺️</div><p>PLZ oder Adresse eingeben<br>und <strong>Suchen</strong> klicken</p></div>
    </div>
  </div>
</div>
<div id="hist-modal" onclick="closeHistModal(event)">
  <div class="hist-box">
    <div class="hist-head">
      <span class="hist-title" id="hist-station-name">Preishistorie</span>
      <button class="hist-close" onclick="document.getElementById('hist-modal').classList.remove('on')">×</button>
    </div>
    <div class="hist-body">
      <div class="hist-fuel-tabs">
        <button class="hf-btn" data-hfuel="e5" onclick="setHistFuel('e5')">E5</button>
        <button class="hf-btn active" data-hfuel="e10" onclick="setHistFuel('e10')">E10</button>
        <button class="hf-btn" data-hfuel="diesel" onclick="setHistFuel('diesel')">Diesel</button>
      </div>
      <div id="hist-chart-area"></div>
      <div class="hist-stats" id="hist-stats"></div>
    </div>
  </div>
</div>
<button id="scroll-btn" onclick="document.getElementById('list-panel').scrollIntoView({behavior:'smooth'})">
  ↓ Ergebnisse
</button>
<div id="toast"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const S={mode:'plz',fuel:'e10',coords:null,radius:10,stations:[],favorites:[],loading:false,refreshTimer:null,countdownTimer:null,REFRESH:600000,histData:null,histFuel:'e10'};
const map=L.map('map',{center:[51.1657,10.4515],zoom:6});
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> | <a href="https://www.tankerkoenig.de">Tankerkönig</a>',maxZoom:19}).addTo(map);
let markers=[],circle=null;
function clearMap(){markers.forEach(m=>map.removeLayer(m));markers=[];if(circle){map.removeLayer(circle);circle=null;}}
function mkIcon(cheap,isFav,p){
  const color=cheap?'#22c55e':isFav?'#f5a623':'#2a6496';
  const glow=cheap?'filter:drop-shadow(0 0 5px rgba(34,197,94,.6));':isFav?'filter:drop-shadow(0 0 5px rgba(245,166,35,.5));':'';
  return L.divIcon({className:'',html:`<div style="width:28px;height:28px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);background:${color};border:2px solid rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;${glow}"><span style="transform:rotate(45deg);font-family:'IBM Plex Mono',monospace;font-size:7px;font-weight:700;color:#fff">${cheap?'✓':p||'?'}</span></div>`,iconSize:[28,28],iconAnchor:[9,28],popupAnchor:[5,-28]});
}
function fp(v){if(!v||v<=0)return null;return v.toFixed(3);}
function pdHtml(v){const p=fp(v);return p?`<span class="pu-val">${p.slice(0,-1)}<sup style="font-size:8px">${p.slice(-1)}</sup></span>`:`<span class="pu-val na">—</span>`;}
function renderMarkers(stations,fuel){
  clearMap();if(!stations.length)return;
  const wp=stations.filter(s=>s[fuel]>0);
  const cheapest=wp.length?wp.reduce((a,b)=>a[fuel]<b[fuel]?a:b):null;
  stations.forEach(s=>{
    const cheap=cheapest&&s.id===cheapest.id,isFav=S.favorites.includes(s.id),p=fp(s[fuel]);
    const addr=[s.street,s.houseNumber].filter(Boolean).join(' ');
    const openB=s.isOpen?'<span class="open-badge open">Geöffnet</span>':'<span class="open-badge closed">Geschlossen</span>';
    const popup=`<div class="pu"><div class="pu-brand">${s.brand||'Freie Tankstelle'}</div><div class="pu-addr">${addr||''} ${s.postCode||''} ${s.place||''}</div><div class="pu-prices"><div class="pu-pi"><span class="pu-lbl">E5</span>${pdHtml(s.e5)}</div><div class="pu-pi"><span class="pu-lbl">E10</span>${pdHtml(s.e10)}</div><div class="pu-pi"><span class="pu-lbl">Diesel</span>${pdHtml(s.diesel)}</div></div><div class="pu-foot">${openB}${cheap?'<span style="color:var(--green);font-family:Barlow Condensed,sans-serif;font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase">✓ Günstigste</span>':''}</div></div>`;
    const m=L.marker([s.lat,s.lng],{icon:mkIcon(cheap,isFav,p)}).bindPopup(popup);
    m.on('click',()=>hlCard(s.id));m.addTo(map);markers.push(m);
  });
  if(S.coords)circle=L.circle([S.coords.lat,S.coords.lon],{radius:S.radius*1000,color:'rgba(245,166,35,.35)',fillColor:'rgba(245,166,35,.03)',fillOpacity:1,weight:1,dashArray:'4 6'}).addTo(map);
  map.fitBounds(L.latLngBounds(stations.map(s=>[s.lat,s.lng])).pad(.2));
}
function renderList(stations,fuel){
  const list=document.getElementById('station-list'),cnt=document.getElementById('stn-count');
  if(!stations.length){list.innerHTML=`<div class="placeholder"><div class="ico">😕</div><p>Keine Tankstellen gefunden.</p></div>`;cnt.style.display='none';return;}
  const sorted=[...stations].sort((a,b)=>{const pa=a[fuel]>0?a[fuel]:1e9,pb=b[fuel]>0?b[fuel]:1e9;return pa-pb;});
  cnt.textContent=`${stations.length} Stationen`;cnt.style.display='inline-block';
  const favs=sorted.filter(s=>S.favorites.includes(s.id)),rest=sorted.filter(s=>!S.favorites.includes(s.id));
  const cheapestId=sorted.find(s=>s[fuel]>0)?.id;
  let html='';
  if(favs.length){html+=`<div class="section-sep"><div class="sep-line"></div><span class="sep-label">★ Meine Favoriten</span><div class="sep-line"></div></div>`;favs.forEach((s,i)=>{html+=cardHtml(s,i+1,fuel,cheapestId,true);});}
  if(rest.length){if(favs.length)html+=`<div class="section-sep"><div class="sep-line"></div><span class="sep-label">Weitere Tankstellen</span><div class="sep-line"></div></div>`;rest.forEach((s,i)=>{html+=cardHtml(s,favs.length+i+1,fuel,cheapestId,false);});}
  list.innerHTML=html;
}
function cardHtml(s,rank,fuel,cheapestId,isFav){
  const p=s[fuel]>0?fp(s[fuel]):null,cheap=s.id===cheapestId&&p!=null;
  const addr=[s.street,s.houseNumber].filter(Boolean).join(' ');
  const brand=s.brand||'Freie Tankstelle';
  const priceEl=p?`<div class="price-big ${cheap?'cheapest':isFav?'fav-price':''}">${p.slice(0,-1)}<sup class="price-sup">${p.slice(-1)}</sup></div><span class="price-unit">€/L</span>`:`<div class="price-big na">nicht verfügbar</div>`;
  return `<div class="stn-card ${isFav?'fav-card':''} ${cheap&&!isFav?'cheapest-card':''}" data-id="${s.id}" onclick="onCard('${s.id}')">
    ${cheap?'<div class="crown">✓</div>':''}
    <div class="card-left"><span class="rank-num">${rank}</span><button class="fav-btn ${isFav?'active':''}" onclick="toggleFav('${s.id}',event)" title="${isFav?'Favorit entfernen':'Als Favorit speichern'}">${isFav?'\u2605':'\u2606'}</button></div>
    <div class="card-info">
      <div class="card-brand">${brand}</div>
      <div class="card-addr">${addr||'—'}</div>
      <div class="card-meta"><span class="dist-badge">${s.dist!=null?s.dist.toFixed(1)+' km':''}</span><span class="open-badge ${s.isOpen?'open':'closed'}">${s.isOpen?'Offen':'Zu'}</span><button class="hist-btn" onclick="openHist('${s.id}','${brand.replace(/'/g,"\\'")}',event)">📈 Verlauf</button></div>
    </div>
    <div class="card-price">${priceEl}</div>
  </div>`;
}
function hlCard(id){document.querySelectorAll('.stn-card').forEach(el=>el.style.outline='');const c=document.querySelector(`.stn-card[data-id="${id}"]`);if(c){c.scrollIntoView({behavior:'smooth',block:'nearest'});c.style.outline='1px solid rgba(245,166,35,.5)';}}
function onCard(id){const s=S.stations.find(x=>x.id===id);if(!s)return;map.setView([s.lat,s.lng],15);const m=markers.find(mk=>{const l=mk.getLatLng();return Math.abs(l.lat-s.lat)<1e-5&&Math.abs(l.lng-s.lng)<1e-5;});if(m)m.openPopup();}
async function loadFavorites(){
  try{
    const stored=localStorage.getItem('spritpreis_favorites');
    S.favorites=stored?JSON.parse(stored):[];
  }catch(e){S.favorites=[];}
}
async function toggleFav(id,e){
  e.stopPropagation();
  const isFav=S.favorites.includes(id);
  if(isFav){S.favorites=S.favorites.filter(f=>f!==id);}
  else{S.favorites.push(id);}
  try{localStorage.setItem('spritpreis_favorites',JSON.stringify(S.favorites));}catch(e){}
  if(S.stations.length){renderMarkers(S.stations,S.fuel);renderList(S.stations,S.fuel);}
  toast(isFav?'Favorit entfernt':'Als Favorit gespeichert ★',isFav?'':'ok');
}
async function openHist(id,name,e){
  e.stopPropagation();
  document.getElementById('hist-station-name').textContent=name;
  document.getElementById('hist-chart-area').innerHTML='<div class="hist-empty">Lade…</div>';
  document.getElementById('hist-stats').innerHTML='';
  document.getElementById('hist-modal').classList.add('on');
  try{const r=await fetch(`/api/history/${id}`);S.histData=await r.json();S.histData._id=id;drawHistChart(S.histFuel);}
  catch(e){document.getElementById('hist-chart-area').innerHTML='<div class="hist-empty">Keine Daten</div>';}
}
function closeHistModal(e){if(e.target===document.getElementById('hist-modal'))document.getElementById('hist-modal').classList.remove('on');}
function setHistFuel(f){S.histFuel=f;document.querySelectorAll('.hf-btn').forEach(b=>b.classList.toggle('active',b.dataset.hfuel===f));if(S.histData)drawHistChart(f);}
function drawHistChart(fuel){
  const area=document.getElementById('hist-chart-area'),stats=document.getElementById('hist-stats');
  const prices=(S.histData?.prices||[]).filter(p=>p[fuel]!=null&&p[fuel]>0);
  if(prices.length<2){area.innerHTML='<div class="hist-empty">Noch nicht genug Daten.<br>Die Historie wächst mit jedem Abruf.</div>';stats.innerHTML='';return;}
  const vals=prices.map(p=>p[fuel]),times=prices.map(p=>new Date(p.ts));
  const minV=Math.min(...vals),maxV=Math.max(...vals),avgV=vals.reduce((a,b)=>a+b)/vals.length;
  const range=maxV-minV||0.01;
  const W=480,H=140,P={t:12,r:12,b:28,l:50};
  const iw=W-P.l-P.r,ih=H-P.t-P.b;
  const xs=i=>P.l+i*(iw/(prices.length-1)),ys=v=>P.t+ih-(((v-minV)/range)*ih);
  const pts=vals.map((v,i)=>`${i===0?'M':'L'}${xs(i).toFixed(1)},${ys(v).toFixed(1)}`).join(' ');
  const ap=`${pts} L${xs(vals.length-1).toFixed(1)},${(P.t+ih).toFixed(1)} L${P.l.toFixed(1)},${(P.t+ih).toFixed(1)} Z`;
  const yL=[minV,minV+range/2,maxV].map(v=>`<text x="${P.l-6}" y="${ys(v)+4}" text-anchor="end" font-size="9" fill="#7c7f8a">${v.toFixed(3)}</text>`).join('');
  const fmt=d=>`${d.getDate()}.${d.getMonth()+1}. ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
  const xL=`<text x="${P.l}" y="${H-6}" font-size="9" fill="#7c7f8a">${fmt(times[0])}</text><text x="${W-P.r}" y="${H-6}" text-anchor="end" font-size="9" fill="#7c7f8a">${fmt(times[times.length-1])}</text>`;
  const lc=fuel==='diesel'?'#60a5fa':fuel==='e5'?'#f59e0b':'#f5a623';
  area.innerHTML=`<div class="hist-canvas-wrap"><svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%"><defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${lc}" stop-opacity=".3"/><stop offset="100%" stop-color="${lc}" stop-opacity=".02"/></linearGradient></defs><path d="${ap}" fill="url(#ag)"/><path d="${pts}" fill="none" stroke="${lc}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>${yL}${xL}</svg></div>`;
  stats.innerHTML=`<div class="stat-box"><span class="stat-label">Aktuell</span><span class="stat-val">${vals[vals.length-1].toFixed(3)}</span></div><div class="stat-box"><span class="stat-label">Min</span><span class="stat-val low">${minV.toFixed(3)}</span></div><div class="stat-box"><span class="stat-label">Max</span><span class="stat-val high">${maxV.toFixed(3)}</span></div>`;
}
function setMode(m){
  S.mode=m;
  document.querySelectorAll('.mode-btn').forEach(b=>b.classList.toggle('active',(b.textContent==='PLZ'&&m==='plz')||(b.textContent==='Adresse'&&m==='addr')));
  document.getElementById('plz-input').style.display=m==='plz'?'block':'none';
  document.getElementById('addr-input').style.display=m==='addr'?'block':'none';
  document.getElementById('search-label').textContent=m==='plz'?'Postleitzahl':'Adresse / Straße';
}
async function geocode(){
  if(S.mode==='plz'){
    const plz=document.getElementById('plz-input').value.trim();
    if(!/^\d{5}$/.test(plz)){document.getElementById('plz-input').classList.add('error');toast('Bitte 5-stellige PLZ eingeben','err');return null;}
    document.getElementById('plz-input').classList.remove('error');
    const r=await fetch(`/api/geocode?plz=${plz}`);if(!r.ok){const e=await r.json().catch(()=>{});throw new Error(e?.error||'Geocoding fehlgeschlagen');}return r.json();
  }else{
    const q=document.getElementById('addr-input').value.trim();
    if(!q){document.getElementById('addr-input').classList.add('error');toast('Bitte Adresse eingeben','err');return null;}
    document.getElementById('addr-input').classList.remove('error');
    const r=await fetch(`/api/geocode?q=${encodeURIComponent(q)}`);if(!r.ok){const e=await r.json().catch(()=>{});throw new Error(e?.error||'Adresse nicht gefunden');}return r.json();
  }
}
async function doSearch(){
  setLoad(true);setStatus('info','Standort wird ermittelt…');
  try{
    const coords=await geocode();if(!coords){setLoad(false);return;}
    S.coords=coords;S.radius=parseInt(document.getElementById('radius-sel').value);
    setStatus('info','Tankstellen werden abgerufen (Tankerkönig)…');
    const data=await fetch(`/api/stations?lat=${coords.lat}&lng=${coords.lon}&rad=${S.radius}`).then(r=>{if(!r.ok)return r.json().then(e=>{throw new Error(e.error||'Fehler');});return r.json();});
    S.stations=data.stations;renderMarkers(S.stations,S.fuel);renderList(S.stations,S.fuel);
    if(window.innerWidth<=768)document.getElementById('scroll-btn').classList.add('visible');
    setStatus('success',`${S.stations.length} Tankstellen (Quelle: Tankerkönig) – ${S.radius} km Umkreis`);
    toast(`${S.stations.length} Tankstellen gefunden`,'ok');startRefresh();
  }catch(e){setStatus('error',`Fehler: ${e.message}`);toast(e.message,'err');}
  finally{setLoad(false);}
}
async function doRefresh(){
  if(!S.coords||S.loading)return;setLoad(true);
  try{const data=await fetch(`/api/stations?lat=${S.coords.lat}&lng=${S.coords.lon}&rad=${S.radius}`).then(r=>r.json());S.stations=data.stations;renderMarkers(S.stations,S.fuel);renderList(S.stations,S.fuel);setStatus('success',`${S.stations.length} Tankstellen – ${new Date().toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'})} Uhr`);}
  catch(e){setStatus('error','Aktualisierung fehlgeschlagen');}finally{setLoad(false);}
}
let nextRefresh=null;
function startRefresh(){
  clearRefresh();
  S.refreshTimer=setInterval(()=>{doRefresh();nextRefresh=Date.now()+S.REFRESH;},S.REFRESH);
  nextRefresh=Date.now()+S.REFRESH;
  S.countdownTimer=setInterval(()=>{const r=Math.max(0,nextRefresh-Date.now()),m=Math.floor(r/60000),s=Math.floor((r%60000)/1000);document.getElementById('countdown').textContent=`${m}:${s.toString().padStart(2,'0')}`;},1000);
  document.getElementById('refresh-badge').classList.add('active');
}
function clearRefresh(){if(S.refreshTimer)clearInterval(S.refreshTimer);if(S.countdownTimer)clearInterval(S.countdownTimer);}
function setLoad(on){S.loading=on;document.getElementById('map-loader').classList.toggle('on',on);document.getElementById('search-btn').disabled=on;}
function setStatus(t,msg){const bar=document.getElementById('status-bar'),txt=document.getElementById('status-txt'),ico=document.getElementById('status-ico');bar.className='visible'+(t==='error'?' err':'');txt.textContent=msg;const icons={info:'<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/>',success:'<polyline points="20 6 9 17 4 12"/>',error:'<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>'};ico.innerHTML=icons[t]||icons.info;}
function toast(msg,type=''){const t=document.getElementById('toast');t.textContent=msg;t.className=`show ${type}`;clearTimeout(t._t);t._t=setTimeout(()=>t.className='',3000);}
document.querySelectorAll('.fuel-btn').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.fuel-btn').forEach(x=>x.classList.remove('active'));
  b.classList.add('active');S.fuel=b.dataset.fuel;
  if(S.coords){doRefresh();}
  else if(S.stations.length){renderMarkers(S.stations,S.fuel);renderList(S.stations,S.fuel);}
}));
document.getElementById('radius-sel').addEventListener('change',()=>{
  S.radius=parseInt(document.getElementById('radius-sel').value);
  if(S.coords) doRefresh();
});
document.getElementById('plz-input').addEventListener('keydown',e=>{if(e.key==='Enter')doSearch();if(e.key.length===1&&!/\d/.test(e.key))e.preventDefault();});
document.getElementById('plz-input').addEventListener('input',e=>{e.target.classList.remove('error');e.target.value=e.target.value.replace(/\D/g,'').slice(0,5);});
document.getElementById('addr-input').addEventListener('keydown',e=>{if(e.key==='Enter')doSearch();});
document.getElementById('addr-input').addEventListener('input',e=>e.target.classList.remove('error'));
document.addEventListener('keydown',e=>{if(e.key==='Escape')document.getElementById('hist-modal').classList.remove('on');});
loadFavorites();
</script>
</body>
</html>"""

# ── Lokaler Start ────────────────────────────────────────
def open_browser():
    time.sleep(1.3)
    webbrowser.open(f"http://localhost:{PORT}")

if __name__ == "__main__":
    if not TANKERKOENIG_API_KEY:
        print("⚠️  TANKERKOENIG_API_KEY nicht gesetzt!")
        print("   export TANKERKOENIG_API_KEY='dein-key'\n")

    if IS_LOCAL:
        print(f"""
╔══════════════════════════════════════════════════╗
║    ⛽  Spritpreis-Tracker  v3                    ║
║    Quelle: Tankerkönig API (CC BY 4.0)           ║
╠══════════════════════════════════════════════════╣
║  URL:     http://localhost:{PORT}                   ║
║  Daten:   ~/.spritpreis_tracker/                 ║
║  Beenden: Strg+C                                 ║
╚══════════════════════════════════════════════════╝
""")
        threading.Thread(target=open_browser, daemon=True).start()

    try:
        app.run(
            host="0.0.0.0" if not IS_LOCAL else "127.0.0.1",
            port=PORT,
            debug=False,
            use_reloader=False,
        )
    except KeyboardInterrupt:
        print("\n👋 Auf Wiedersehen!")
        sys.exit(0)
