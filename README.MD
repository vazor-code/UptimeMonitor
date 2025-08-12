# 🚀 UptimeMonitor Pro

A powerful, real-time website monitoring system with Telegram alerts, dark mode, and multi-language support.

![Flask](https://img.shields.io/badge/Flask-3.0.3-green)
![Python](https://img.shields.io/badge/Python-3.10+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

🌍 **Languages:** RU / EN  
🔔 **Telegram alerts on downtime**  
📊 **Live charts & admin stats**  
🌙 **Dark/Light mode (saved)**  
🌐 **Works in restricted regions (Mobile-ready)**

---

## 📸 Screenshots

### Dashboard (Light)
![Dashboard Light](screenshots/dashboard-light.png)

### Dashboard (Dark)
![Dashboard Dark](screenshots/dashboard-dark.png)

---

## 🔧 Features

- ✅ Real-time updates via SSE
- ✅ Telegram notifications on site failure
- ✅ SSL certificate expiry warnings
- ✅ Multi-language (Russian / English)
- ✅ Dark & Light theme (persists)
- ✅ Admin panel with uptime charts
- ✅ Auto-detect browser language
- ✅ IPv6 & HTTPS support

---

## 📦 Setup

```bash
# 1. Clone the repo
git clone https://github.com/vazor-code/UptimeMonitor.git
cd UptimeMonitor

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env from example
cp .env.example .env
# Open .env and put your values

# 5. Run the app
python app.py
```

## 📬 Feedback
Found a bug? Want a feature?
Open an issue or contact me: scoutboy0202@gmail.com

## 🎉 Credits
Made with ❤️ by vazor
2025 · MIT License