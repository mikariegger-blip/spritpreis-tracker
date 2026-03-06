# ⛽ Spritpreis-Tracker – Deployment-Anleitung

Zwei kostenlose Hosting-Optionen: **Railway** (empfohlen, einfacher) oder **Render**.
Ziel: Ein Link wie `https://mein-spritpreis.railway.app` den du einfach per WhatsApp teilen kannst.

---

## Vorbereitung: GitHub-Repository anlegen (einmalig, 5 Minuten)

GitHub ist eine kostenlose Plattform zum Speichern von Code.
Railway und Render holen sich die App von dort automatisch.

1. Gehe zu **https://github.com** → Account erstellen (falls noch keiner vorhanden)
2. Klicke oben rechts auf **„+"** → **„New repository"**
3. Name: `spritpreis-tracker` → **„Create repository"**
4. Auf der nächsten Seite siehst du Befehle. Öffne dein Terminal und gib ein:

```bash
cd ~/Desktop              # oder wo auch immer deine Dateien liegen
mkdir spritpreis-tracker
cd spritpreis-tracker
cp /pfad/zu/app.py .
cp /pfad/zu/requirements.txt .
cp /pfad/zu/Dockerfile .
cp /pfad/zu/railway.toml .

git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/DEIN-USERNAME/spritpreis-tracker.git
git push -u origin main
```

> Ersetze `DEIN-USERNAME` mit deinem GitHub-Benutzernamen.

---

## Option A: Railway (empfohlen – am schnellsten)

### Schritt 1: Account anlegen
→ https://railway.app → **„Start a New Project"** → mit GitHub einloggen

### Schritt 2: Projekt erstellen
1. Klicke **„Deploy from GitHub repo"**
2. Wähle `spritpreis-tracker` aus der Liste
3. Railway erkennt das `Dockerfile` automatisch

### Schritt 3: API-Key als Secret hinterlegen ⚠️
> Dieser Schritt ist wichtig – ohne Key gibt es keine Preise!

1. Im Railway-Dashboard: Dein Projekt → **„Variables"** (linke Leiste)
2. Klicke **„New Variable"**
3. Name:  `TANKERKOENIG_API_KEY`
   Wert:  `3e1db9cb-51dc-4163-a8d4-6f1512a9997b`
4. **„Add"** klicken → Railway deployt automatisch neu

### Schritt 4: URL abrufen
1. Im Dashboard → **„Settings"** → **„Domains"**
2. Klicke **„Generate Domain"**
3. Du bekommst eine URL wie: `https://spritpreis-tracker-production.railway.app`

✅ **Fertig! Diese URL an Freunde schicken – funktioniert direkt im Handy-Browser.**

### Kosten Railway
- Free Tier: **500 Stunden/Monat** kostenlos (reicht für 24/7 Betrieb ~20 Tage)
- Danach: Hobby Plan für $5/Monat (unbegrenzt)
- Alternativ: App nur auf Anfrage starten lassen (spart Stunden)

---

## Option B: Render (komplett kostenlos, aber langsamer Start)

### Schritt 1: Account
→ https://render.com → **„Get Started for Free"** → mit GitHub einloggen

### Schritt 2: Neuen Web Service erstellen
1. **„New +"** → **„Web Service"**
2. **„Connect a repository"** → `spritpreis-tracker` auswählen
3. Einstellungen:
   - **Name:** `spritpreis-tracker`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 30`
   - **Plan:** Free

### Schritt 3: API-Key hinterlegen
1. Scroll runter zu **„Environment Variables"**
2. **„Add Environment Variable"**:
   - Key:   `TANKERKOENIG_API_KEY`
   - Value: `3e1db9cb-51dc-4163-a8d4-6f1512a9997b`
3. **„Create Web Service"** klicken

### Schritt 4: URL
Render gibt dir automatisch eine URL wie:
`https://spritpreis-tracker.onrender.com`

### ⚠️ Hinweis Render Free Plan
Auf dem Free Plan schläft die App nach 15 Minuten Inaktivität ein.
Beim ersten Aufruf danach dauert es ~30 Sekunden bis sie aufwacht.
Das ist normal und kostenlos – einfach kurz warten.

---

## Als Handy-App (PWA) hinzufügen

Damit die App auf dem Homescreen erscheint wie eine echte App:

**iPhone (Safari):**
1. URL öffnen → Teilen-Symbol (Kästchen mit Pfeil nach oben)
2. **„Zum Home-Bildschirm"** tippen
3. Name bestätigen → **„Hinzufügen"**

**Android (Chrome):**
1. URL öffnen → Drei-Punkte-Menü oben rechts
2. **„Zum Startbildschirm hinzufügen"**
3. Bestätigen

---

## Updates deployen (später)

Wenn du Änderungen an `app.py` machst:
```bash
git add app.py
git commit -m "Update"
git push
```
→ Railway/Render deployt automatisch neu (dauert ~1-2 Minuten).

---

## Lokale Nutzung (ohne Hosting)

```bash
pip3 install flask requests
export TANKERKOENIG_API_KEY="3e1db9cb-51dc-4163-a8d4-6f1512a9997b"
python3 app.py
# → http://localhost:7331
```

---

## Datenschutz-Hinweis

Die App speichert:
- Favoriten (Station-IDs) – lokal auf dem Server in `/tmp`
- Preishistorie – lokal auf dem Server in `/tmp`
- **Keine personenbezogenen Daten**, keine Cookies, kein Tracking

Hinweis: Auf Render/Railway wird `/tmp` bei jedem Neustart geleert (Favoriten gehen verloren).
Für dauerhaften Speicher wäre eine kleine Datenbank (z.B. Railway PostgreSQL) nötig.
