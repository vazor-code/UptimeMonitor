# app.py
import os
import time
import requests
import sqlite3
import ssl
import socket
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask, render_template, request, redirect, url_for, Response, jsonify
import json
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
DB_NAME = "sites.db"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Load translations from JSON files
def load_translations():
    translations = {}
    for lang in ['ru', 'en']:
        with open(f"templates/lang/{lang}.json", "r", encoding="utf-8") as f:
            translations[lang] = json.load(f)
    return translations

TRANSLATIONS = load_translations()

@app.context_processor
def inject_lang():
    # Get language from URL parameter, default is 'ru'
    lang = request.args.get('lang', 'ru')  # /?lang=en
    t = TRANSLATIONS.get(lang, TRANSLATIONS['ru'])
    return dict(t=t, lang=lang)

# === Safe database connection (thread-safe) ===
def get_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

# === Initialize the database ===
def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                check_interval INTEGER DEFAULT 60,
                expected_text TEXT,
                enabled INTEGER DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER,
                status INTEGER,
                response_time REAL,
                timestamp TEXT,
                FOREIGN KEY (site_id) REFERENCES sites (id)
            )
        """)

# === Check SSL certificate expiration ===
def check_ssl_expiry(hostname, port=443):
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                expiry_str = cert['notAfter']
                expiry_date = datetime.strptime(expiry_str, '%b %d %H:%M:%S %Y %Z')
                days_left = (expiry_date - datetime.utcnow()).days
                return days_left, expiry_date.strftime('%Y-%m-%d')
    except Exception as e:
        return None, str(e)

# === Check website status ===
def check_site(site):
    site_id = site[0]
    url = site[1]
    expected_text = site[3]
    start = time.time()

    ssl_info = None
    if url.startswith("https://"):
        hostname = url.split("://")[1].split("/")[0].split(":")[0]
        days_left, expiry = check_ssl_expiry(hostname)
        if days_left is not None:
            ssl_info = f"SSL: expires {expiry} ({days_left} days left)"
            if days_left < 7:
                send_telegram(f"⚠️ <b>SSL will expire soon!</b>\n\n🌐 <code>{url}</code>\n📅 Left: {days_left} days")

    try:
        r = requests.get(url, timeout=10, headers={'User-Agent': 'UptimeMonitor/1.0'})
        response_time = time.time() - start
        content_ok = True
        if expected_text and expected_text.strip():
            content_ok = expected_text in r.text
        status = 1 if (r.status_code == 200 and content_ok) else 0
    except Exception:
        response_time = None
        status = 0

    # Log the result
    with get_db() as conn:
        conn.execute(
            "INSERT INTO logs (site_id, status, response_time, timestamp) VALUES (?, ?, ?, ?)",
            (site_id, status, response_time, datetime.now().isoformat())
        )

    # Send alert if site is down
    if status == 0:
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if response_time is None:
            reason = "❌ Not responding (timeout)"
        elif r.status_code != 200:
            reason = f"⚠️ HTTP status: {r.status_code}"
        else:
            reason = f"🔍 Expected text '{expected_text}' not found"

        message = f"""🔴 <b>SITE IS DOWN</b>

🌐 <b>Site:</b> <code>{url}</code>
🕒 <b>Time:</b> {current_time}
⏱️ <b>Response:</b> {f'{response_time:.3f} s' if response_time else '—'}
📝 <b>Expected text:</b> <code>{expected_text or '—'}</code>
🔄 <b>Interval:</b> {site[2]} s
{"🔐 " + ssl_info if ssl_info else ''}

📋 <b>Reason:</b>
{reason}

🔧 <b>What to do?</b>
➡️ Check the server
➡️ Make sure the site is accessible

📊 <b>Monitoring:</b>
<a href="http://localhost:5000">Open panel</a>
"""

        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            send_telegram(message)
        else:
            print("ℹ️ Telegram is not configured")

    return status

# === Send message to Telegram ===
def send_telegram(message):
    try:
        # ✅ Removed extra spaces in URL!
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        response = requests.post(url, data=data, timeout=10)
        if response.status_code == 200:
            print("✅ Notification sent to Telegram")
        else:
            print(f"❌ Error: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"⚠️ Telegram error: {e}")

# === Background polling loop ===
def polling_loop():
    print("✅ Monitoring started...")
    while True:
        try:
            with get_db() as conn:
                sites = conn.execute("SELECT id, url, check_interval, expected_text FROM sites WHERE enabled = 1").fetchall()
            for site in sites:
                check_site(site)
                time.sleep(1)
            time.sleep(10)
        except Exception as e:
            print(f"🚨 Error: {e}")
            time.sleep(10)

def start_polling():
    thread = Thread(target=polling_loop, daemon=True)
    thread.start()

# === Web routes ===
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form["url"].strip()
        interval = max(10, int(request.form.get("interval", 60)))
        text = request.form.get("text", "").strip()
        if url:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO sites (url, check_interval, expected_text) VALUES (?, ?, ?)",
                    (url, interval, text or None)
                )
        return redirect(url_for("index"))

    with get_db() as conn:
        sites = conn.execute("""
            SELECT 
                s.id, s.url, s.check_interval, s.expected_text, s.enabled,
                l.status, l.response_time, l.timestamp,
                (SELECT COUNT(*) FROM logs WHERE site_id = s.id AND status = 1) * 100.0 / 
                (SELECT COUNT(*) FROM logs WHERE site_id = s.id) AS uptime_percent
            FROM sites s
            LEFT JOIN logs l ON l.id = (
                SELECT id FROM logs WHERE site_id = s.id ORDER BY timestamp DESC LIMIT 1
            )
            ORDER BY s.url
        """).fetchall()

    return render_template("index.html", sites=sites)

@app.route("/toggle/<int:site_id>")
def toggle(site_id):
    with get_db() as conn:
        site = conn.execute("SELECT enabled FROM sites WHERE id = ?", (site_id,)).fetchone()
        new_state = 0 if site[0] else 1
        conn.execute("UPDATE sites SET enabled = ? WHERE id = ?", (new_state, site_id))
    return redirect(url_for("index"))

@app.route("/delete/<int:site_id>")
def delete(site_id):
    with get_db() as conn:
        conn.execute("DELETE FROM sites WHERE id = ?", (site_id,))
        conn.execute("DELETE FROM logs WHERE site_id = ?", (site_id,))
    return redirect(url_for("index"))

@app.route("/api/logs/<int:site_id>")
def api_logs(site_id):
    days = request.args.get("days", 7, type=int)
    since = datetime.now() - timedelta(days=days)
    with get_db() as conn:
        logs = conn.execute("""
            SELECT status, response_time, timestamp FROM logs
            WHERE site_id = ? AND timestamp > ?
            ORDER BY timestamp
        """, (site_id, since.isoformat())).fetchall()
    return Response(json.dumps([
        {"x": log[2].split(".")[0].replace("T", " "), "y": round(log[1], 3) if log[1] else None}
        for log in logs
    ]), mimetype='application/json')

@app.route("/stream")
def stream():
    def event_stream():
        while True:
            with get_db() as conn:
                sites = conn.execute("""
                    SELECT s.id, s.url, s.enabled, l.status, l.response_time, l.timestamp
                    FROM sites s
                    LEFT JOIN logs l ON l.id = (
                        SELECT id FROM logs WHERE site_id = s.id ORDER BY timestamp DESC LIMIT 1
                    )
                """).fetchall()
            data = [
                {
                    "id": s[0], "url": s[1], "enabled": s[2],
                    "status": "up" if s[3] == 1 else "down",
                    "response_time": round(s[4], 3) if s[4] else None,
                    "timestamp": s[5].split('.')[0].replace('T', ' ') if s[5] else None
                }
                for s in sites
            ]
            yield f"data: {json.dumps(data)}\n\n"
            time.sleep(5)
    return Response(event_stream(), mimetype="text/event-stream")

@app.route("/admin")
def admin():
    with get_db() as conn:
        # General statistics
        total = conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM sites WHERE enabled = 1").fetchone()[0]
        up_now = conn.execute("""
            SELECT COUNT(*) FROM sites s
            JOIN logs l ON l.id = (SELECT id FROM logs WHERE site_id = s.id ORDER BY timestamp DESC LIMIT 1)
            WHERE l.status = 1
        """).fetchone()[0]
        down_now = active - up_now

        # Last 10 events
        events = conn.execute("""
            SELECT s.url, l.status, l.response_time, l.timestamp
            FROM logs l
            JOIN sites s ON s.id = l.site_id
            ORDER BY l.timestamp DESC
            LIMIT 10
        """).fetchall()

        # All sites (for test data)
        all_sites = conn.execute("SELECT url FROM sites WHERE enabled = 1").fetchall()
        all_sites = [s[0] for s in all_sites]  # ['https://google.com', 'https://yandex.ru', ...]

    return render_template("admin.html", 
        total=total, 
        active=active, 
        down_now=down_now, 
        up_now=up_now,
        events=events,
        all_sites=all_sites  # Pass to template
    )

@app.route("/api/downtime-stats")
def downtime_stats():
    days = 30
    since = datetime.now() - timedelta(days=days)
    stats = {}
    with get_db() as conn:
        logs = conn.execute("""
            SELECT l.status, l.response_time, l.timestamp
            FROM logs l
            WHERE l.timestamp > ?
        """, (since.isoformat(),)).fetchall()
    for log in logs:
        date = log[2].split('T')[0]
        if date not in stats:
            stats[date] = {"down": 0, "slow": 0}
        if log[0] == 0:
            stats[date]["down"] += 1
        elif log[1] and log[1] > 2.0:
            stats[date]["slow"] += 1
    result = {}
    for d, c in stats.items():
        result[d] = "down" if c["down"] > 0 else "slow" if c["slow"] > 0 else "up"
    return result

@app.route("/api/admin/stats")
def admin_stats():
    days = request.args.get("days", default=7, type=int)
    days = max(1, days)
    since = f"datetime('now', '-{days} days')"

    with get_db() as conn:
        uptime_data = conn.execute(f"""
            SELECT 
                s.url,
                (SUM(CASE WHEN l.status = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(l.id)) AS uptime
            FROM sites s
            JOIN logs l ON l.site_id = s.id
            WHERE l.timestamp > {since}
            GROUP BY s.id
        """).fetchall()

        avg_response = conn.execute(f"""
            SELECT 
                s.url,
                AVG(l.response_time) AS avg_time
            FROM sites s
            JOIN logs l ON l.site_id = s.id
            WHERE l.status = 1 AND l.timestamp > {since}
            GROUP BY s.id
        """).fetchall()

        downtime_count = conn.execute(f"""
            SELECT 
                s.url,
                COUNT(*) AS down_count
            FROM sites s
            JOIN logs l ON l.site_id = s.id
            WHERE l.status = 0 AND l.timestamp > {since}
            GROUP BY s.id
        """).fetchall()

    return jsonify({
        "uptime": [{"url": row[0], "value": round(row[1], 1)} for row in uptime_data],
        "response": [{"url": row[0], "value": round(row[1] or 0, 3)} for row in avg_response],
        "downtime": [{"url": row[0], "value": row[1]} for row in downtime_count]
    })

# === Start the app ===
if __name__ == "__main__":
    init_db()
    start_polling()
    print("🌐 Web interface: http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)