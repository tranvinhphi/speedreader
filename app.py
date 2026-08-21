# -*- coding: utf-8 -*-
"""
============================================================
  AI ENGLISH SPEED READER
  Version : 3.0.0
  Released: 2026-08-19

  THAY ĐỔI V3.0.0:
  - Hệ thống tài khoản học viên: đăng ký / đăng nhập bằng
    tên + mật khẩu, lưu Supabase (bảng students)
  - Mỗi học viên có thành tích riêng, lịch sử riêng
  - Dashboard cá nhân: WPM trung bình, bài đã đọc, rank
  - Crawl RSS lấy đủ bài (giảm filter, dùng full content)
  - Fix SyntaxWarning backslash trong JS string
  - Fix Supabase SQL policy IF NOT EXISTS
  - Version badge hiển thị trong UI

  Backend : Flask + feedparser + Supabase
  Deploy  : Render.com
============================================================
"""

APP_VERSION  = "3.1.0"
APP_NAME     = "AI Speed Reader"
APP_RELEASED = "2026-08-21"

import os, re, html, hashlib
from datetime import datetime, timezone
import feedparser
from flask import Flask, jsonify, request, render_template_string, session

try:
    from supabase import create_client
except ImportError:
    create_client = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "speedai-secret-2026")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()
supabase = None
print(f"[INIT] URL={SUPABASE_URL[:30] if SUPABASE_URL else 'MISSING'}")
print(f"[INIT] KEY={SUPABASE_KEY[:15] if SUPABASE_KEY else 'MISSING'}...")
print(f"[INIT] lib={create_client is not None}")
if SUPABASE_URL and SUPABASE_KEY and create_client:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        test = supabase.table("articles").select("id").limit(1).execute()
        print(f"[OK] Supabase connected OK: {SUPABASE_URL[:40]}")
    except Exception as e:
        print(f"[ERROR] Supabase failed: {type(e).__name__}: {e}")
        supabase = None
else:
    print(f"[WARN] Supabase skipped — URL={bool(SUPABASE_URL)} KEY={bool(SUPABASE_KEY)} lib={bool(create_client)}")

# ── Tables ──────────────────────────────────────────────────
T_ARTICLES = "articles"
T_SCORES   = "scores"
T_STUDENTS = "students"   # id, name, password_hash, created_at, streak, total_sessions

# ── Demo articles (khi chưa có Supabase) ────────────────────
DEMO_ARTICLES = [
    {
        "id": "d1", "source": "BBC", "title": "The Rise of Artificial Intelligence",
        "content": "In recent years, artificial intelligence technology has evolved rapidly across industries. From healthcare diagnostics to autonomous vehicles, machine learning models now process billions of data points daily. Researchers at leading universities report that natural language processing systems can now summarize complex scientific papers with over ninety percent accuracy. As adoption accelerates, educators are integrating AI literacy into core curricula to prepare students for a workforce where human and machine collaboration is the new standard. Companies across every sector are racing to adopt AI tools that can analyse data, automate tasks, and generate new ideas faster than ever before.",
        "difficulty": "Easy", "image": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&q=70",
        "url": "", "read_time": "5",
    },
    {
        "id": "d2", "source": "CNN", "title": "The Future of Quantum Computing",
        "content": "Quantum computing is breaking the silicon barrier and pushing the boundaries of what is computationally possible. Scientists at major research labs have demonstrated quantum processors capable of solving problems that would take classical computers thousands of years to complete. Industries from pharmaceuticals to finance are watching closely, eager to harness the power of quantum algorithms for drug discovery, portfolio optimisation, and next-generation cryptography. However significant engineering challenges remain before quantum computers become commercially viable at large scale for everyday users and businesses.",
        "difficulty": "Medium", "image": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&q=70",
        "url": "", "read_time": "7",
    },
    {
        "id": "d3", "source": "Reuters", "title": "Urban Planning in the 21st Century",
        "content": "Designing smarter megacities has become a global priority as urban populations continue to grow at an unprecedented rate. City planners now rely on data analytics, sensor networks, and artificial intelligence to manage traffic flow, reduce energy consumption, and improve public services for millions of residents. Sustainable architecture featuring vertical gardens and solar-integrated glass facades is changing skylines from Singapore to Stockholm. The challenge ahead lies in ensuring that smart city benefits reach all residents regardless of income or neighbourhood, avoiding a future where technology widens social inequality rather than closing it.",
        "difficulty": "Hard", "image": "https://images.unsplash.com/photo-1449824913935-59a10b8d2000?w=600&q=70",
        "url": "", "read_time": "9",
    },
    {
        "id": "d4", "source": "NatGeo", "title": "Deep Ocean Exploration",
        "content": "The deep ocean remains one of the least explored frontiers on our planet Earth. Recent expeditions using remotely operated vehicles have discovered thousands of new species living in the crushing darkness far below the surface. Hydrothermal vents support entire ecosystems powered not by sunlight but by chemical energy from the Earth itself. These remarkable findings challenge our assumptions about where life can thrive and have profound implications for the search for life on other planets and moons within our solar system, particularly on icy worlds like Europa and Enceladus.",
        "difficulty": "Easy", "image": "https://images.unsplash.com/photo-1532094349884-543bc11b234d?w=600&q=70",
        "url": "", "read_time": "4",
    },
]

RSS_FEEDS = {
    "BBC Tech":       "http://feeds.bbci.co.uk/news/technology/rss.xml",
    "BBC World":      "http://feeds.bbci.co.uk/news/world/rss.xml",
    "BBC Science":    "http://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "BBC Business":   "http://feeds.bbci.co.uk/news/business/rss.xml",
    "CNN":            "http://rss.cnn.com/rss/cnn_topstories.rss",
    "CNN Tech":       "http://rss.cnn.com/rss/cnn_tech.rss",
    "Reuters World":  "https://feeds.reuters.com/reuters/worldNews",
    "Reuters Tech":   "https://feeds.reuters.com/reuters/technologyNews",
    "Reuters Biz":    "https://feeds.reuters.com/reuters/businessNews",
    "AP Top":         "https://feeds.apnews.com/rss/apf-topnews",
    "AP World":       "https://feeds.apnews.com/rss/apf-WorldNews",
    "AP Tech":        "https://feeds.apnews.com/rss/apf-technology",
    "NPR":            "https://feeds.npr.org/1001/rss.xml",
    "NPR World":      "https://feeds.npr.org/1004/rss.xml",
    "Guardian World": "https://www.theguardian.com/world/rss",
    "Guardian Tech":  "https://www.theguardian.com/technology/rss",
    "Al Jazeera":     "https://www.aljazeera.com/xml/rss/all.xml",
    "NASA":           "https://www.nasa.gov/rss/dyn/breaking_news.rss",
    "Science Daily":  "https://www.sciencedaily.com/rss/all.xml",
    "Ars Technica":   "http://feeds.arstechnica.com/arstechnica/index",
}

DIFF_IMG = {
    "Easy":   "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&q=70",
    "Medium": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&q=70",
    "Hard":   "https://images.unsplash.com/photo-1507413245164-6160d8298b31?w=600&q=70",
}

# ── Helpers ──────────────────────────────────────────────────
def clean_html(raw):
    if not raw: return ""
    t = re.sub(r"<[^>]+>", " ", raw)
    t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()

def hash_pw(pw):
    return hashlib.sha256(pw.strip().encode()).hexdigest()

def estimate_diff(text):
    wc  = len(text.split())
    avg = sum(len(w) for w in text.split()) / max(wc, 1)
    if avg > 6 or wc > 300: return "Hard"
    if avg > 4.5 or wc > 150: return "Medium"
    return "Easy"

def read_time(text):
    return max(1, round(len(text.split()) / 150))

def calc_rank(wpm, acc):
    if acc >= 95 and wpm >= 130: return "S"
    if acc >= 90 and wpm >= 100: return "A"
    if acc >= 80 and wpm >= 70:  return "B"
    return "C"

# ═══════════════════════════════════════════════════════════
# STUDENT AUTH APIs
# ═══════════════════════════════════════════════════════════

@app.route("/api/auth/register", methods=["POST"])
def api_register():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    pw   = (data.get("password") or "").strip()
    if not name or not pw:
        return jsonify({"success": False, "error": "Vui lòng nhập đầy đủ tên và mật khẩu."}), 400
    if len(pw) < 4:
        return jsonify({"success": False, "error": "Mật khẩu tối thiểu 4 ký tự."}), 400
    if supabase is None:
        # Demo mode: lưu vào session
        session["student"] = {"id": "demo-1", "name": name, "demo": True}
        return jsonify({"success": True, "demo_mode": True,
                        "student": {"id": "demo-1", "name": name}})
    try:
        # Kiểm tra tên đã tồn tại chưa
        existing = supabase.table(T_STUDENTS).select("id").eq("name", name).execute()
        if existing.data:
            return jsonify({"success": False, "error": "Tên học viên đã tồn tại. Vui lòng chọn tên khác hoặc đăng nhập."}), 400
        rec = {
            "name": name, "password_hash": hash_pw(pw),
            "streak": 0, "total_sessions": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        res = supabase.table(T_STUDENTS).insert(rec).execute()
        student = res.data[0]
        session["student"] = {"id": student["id"], "name": student["name"]}
        return jsonify({"success": True, "student": {"id": student["id"], "name": student["name"]}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    pw   = (data.get("password") or "").strip()
    if not name or not pw:
        return jsonify({"success": False, "error": "Vui lòng nhập tên và mật khẩu."}), 400
    if supabase is None:
        session["student"] = {"id": "demo-1", "name": name, "demo": True}
        return jsonify({"success": True, "demo_mode": True,
                        "student": {"id": "demo-1", "name": name, "streak": 0, "total_sessions": 0}})
    try:
        res = supabase.table(T_STUDENTS).select("*").eq("name", name).execute()
        if not res.data:
            return jsonify({"success": False, "error": "Không tìm thấy tài khoản. Hãy đăng ký mới."}), 404
        student = res.data[0]
        if student["password_hash"] != hash_pw(pw):
            return jsonify({"success": False, "error": "Mật khẩu không đúng."}), 401
        session["student"] = {"id": student["id"], "name": student["name"]}
        return jsonify({"success": True,
                        "student": {"id": student["id"], "name": student["name"],
                                    "streak": student.get("streak", 0),
                                    "total_sessions": student.get("total_sessions", 0)}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/api/auth/me", methods=["GET"])
def api_me():
    s = session.get("student")
    if not s:
        return jsonify({"logged_in": False})
    return jsonify({"logged_in": True, "student": s})

# ═══════════════════════════════════════════════════════════
# STUDENT PROFILE & SCORES
# ═══════════════════════════════════════════════════════════

@app.route("/api/student/scores", methods=["GET"])
def api_student_scores():
    s = session.get("student")
    if not s:
        return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401
    if supabase is None:
        return jsonify({"success": True, "demo_mode": True, "scores": []})
    try:
        res = (supabase.table(T_SCORES)
               .select("*")
               .eq("student_id", s["id"])
               .order("created_at", desc=True)
               .limit(50)
               .execute())
        return jsonify({"success": True, "scores": res.data or []})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/save_score", methods=["POST"])
def api_save_score():
    data = request.get_json(force=True, silent=True) or {}
    s    = session.get("student")
    if not s:
        return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401
    record = {
        "student_id":    s["id"],
        "student_name":  s["name"],
        "article_title": data.get("article_title", ""),
        "article_id":    data.get("article_id", ""),
        "wpm":           int(data.get("wpm", 0)),
        "accuracy":      int(data.get("accuracy", 0)),
        "rank":          data.get("rank", "C"),
        "words_read":    int(data.get("words_read", 0)),
        "created_at":    datetime.now(timezone.utc).isoformat(),
    }
    if supabase is None:
        return jsonify({"success": True, "demo_mode": True, "data": record})
    try:
        supabase.table(T_SCORES).insert(record).execute()
        # Cập nhật total_sessions + streak
        supabase.table(T_STUDENTS).update({
            "total_sessions": supabase.table(T_STUDENTS).select("total_sessions").eq("id", s["id"]).execute().data[0]["total_sessions"] + 1
        }).eq("id", s["id"]).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════════════════
# LEADERBOARD
# ═══════════════════════════════════════════════════════════

@app.route("/api/leaderboard", methods=["GET"])
def api_leaderboard():
    if supabase is None:
        return jsonify({"success": True, "demo_mode": True, "leaderboard": [
            {"student_name": "Alex", "best_wpm": 145, "avg_accuracy": 96, "total_sessions": 12, "best_rank": "S"},
            {"student_name": "Mai",  "best_wpm": 120, "avg_accuracy": 92, "total_sessions": 8,  "best_rank": "A"},
            {"student_name": "Nam",  "best_wpm": 95,  "avg_accuracy": 85, "total_sessions": 5,  "best_rank": "B"},
        ]})
    try:
        res = supabase.table(T_SCORES).select("student_name,wpm,accuracy,rank").execute()
        rows = res.data or []
        grouped = {}
        for r in rows:
            n = r["student_name"]
            if n not in grouped:
                grouped[n] = {"student_name": n, "best_wpm": 0, "total_acc": 0, "count": 0, "best_rank": "C"}
            grouped[n]["best_wpm"] = max(grouped[n]["best_wpm"], r["wpm"])
            grouped[n]["total_acc"] += r["accuracy"]
            grouped[n]["count"] += 1
            if "SABC".index(r["rank"]) < "SABC".index(grouped[n]["best_rank"]):
                grouped[n]["best_rank"] = r["rank"]
        board = sorted(grouped.values(), key=lambda x: x["best_wpm"], reverse=True)[:10]
        for b in board:
            b["avg_accuracy"] = round(b["total_acc"] / b["count"]) if b["count"] else 0
            b["total_sessions"] = b.pop("count")
            b.pop("total_acc", None)
        return jsonify({"success": True, "leaderboard": board})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════════════════
# ARTICLES & CRAWL
# ═══════════════════════════════════════════════════════════

@app.route("/api/articles", methods=["GET"])
def api_articles():
    if supabase is None:
        return jsonify({"success": True, "demo_mode": True, "articles": DEMO_ARTICLES})
    try:
        res = (supabase.table(T_ARTICLES)
               .select("*").order("created_at", desc=True).limit(30).execute())
        articles = res.data or []
        if not articles:
            return jsonify({"success": True, "demo_mode": True, "articles": DEMO_ARTICLES})
        return jsonify({"success": True, "articles": articles})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "articles": DEMO_ARTICLES})

@app.route("/api/crawl", methods=["POST"])
def api_crawl():
    found = []
    seen_titles = set()
    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                title = clean_html(entry.get("title", ""))
                if not title or title in seen_titles:
                    continue
                # Lấy nội dung dài nhất
                content = ""
                for field in ["content", "summary", "description"]:
                    val = entry.get(field, "")
                    if isinstance(val, list):
                        val = " ".join(v.get("value","") for v in val if isinstance(v, dict))
                    c = clean_html(val)
                    if len(c) > len(content):
                        content = c
                if len(content.split()) < 10:
                    continue
                # Lấy ngày đăng
                pub = ""
                for tf in ["published_parsed", "updated_parsed"]:
                    t = entry.get(tf)
                    if t:
                        try:
                            pub = datetime(*t[:6], tzinfo=timezone.utc).strftime("%d/%m/%Y")
                        except:
                            pass
                        break
                if not pub:
                    pub = datetime.now(timezone.utc).strftime("%d/%m/%Y")
                diff = estimate_diff(content)
                seen_titles.add(title)
                found.append({
                    "source":      source,
                    "title":       title,
                    "content":     content,
                    "url":         entry.get("link", ""),
                    "difficulty":  diff,
                    "image":       DIFF_IMG.get(diff, DIFF_IMG["Medium"]),
                    "read_time":   str(read_time(content)),
                    "word_count":  len(content.split()),
                    "published":   pub,
                })
        except Exception as e:
            print(f"[CRAWL ERR] {source}: {e}")
    return jsonify({"success": True, "count": len(found), "articles": found})

@app.route("/api/approve", methods=["POST"])
def api_approve():
    data = request.get_json(force=True, silent=True) or {}
    if not data.get("title") or not data.get("content"):
        return jsonify({"success": False, "error": "Thiếu dữ liệu"}), 400
    record = {
        "title":      data["title"],
        "source":     data.get("source",""),
        "url":        data.get("url",""),
        "content":    data["content"],
        "difficulty": data.get("difficulty","Medium"),
        "image":      data.get("image", DIFF_IMG["Medium"]),
        "read_time":  data.get("read_time","5"),
        "published":  data.get("published",""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if supabase is None:
        return jsonify({"success": True, "demo_mode": True, "data": record})
    try:
        res = supabase.table(T_ARTICLES).insert(record).execute()
        return jsonify({"success": True, "data": res.data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/articles/delete/<int:article_id>", methods=["DELETE"])
def api_delete_article(article_id):
    if supabase is None:
        return jsonify({"success": True, "demo_mode": True})
    try:
        supabase.table(T_ARTICLES).delete().eq("id", article_id).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/version")
def api_version():
    return jsonify({"app": APP_NAME, "version": APP_VERSION, "released": APP_RELEASED})

# ═══════════════════════════════════════════════════════════
# SHARED CSS / HEAD
# ═══════════════════════════════════════════════════════════
SHARED_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Merriweather:wght@400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config={theme:{extend:{
  fontFamily:{sans:["Plus Jakarta Sans","sans-serif"],serif:["Merriweather","serif"]},
  colors:{brand:{dark:"#1a252f",blue:"#2563eb",emerald:"#2ecc71",graybg:"#f8fafc"}}
}}}
</script>
<style>
::-webkit-scrollbar{width:6px}::-webkit-scrollbar-thumb{background:#cbd5e1;border-radius:10px}
.no-scrollbar::-webkit-scrollbar{display:none}.no-scrollbar{-ms-overflow-style:none;scrollbar-width:none}
@keyframes pulse-ring{0%{transform:scale(.85);opacity:.6}100%{transform:scale(1.4);opacity:0}}
.pulse-ring::before{content:"";position:absolute;inset:-6px;border-radius:9999px;border:2px solid #2563eb;animation:pulse-ring 2s cubic-bezier(.4,0,.6,1) infinite}
@keyframes wave{0%{height:14%}100%{height:100%}}
.wave-bar{animation:wave 1.2s ease-in-out infinite alternate}
.sidebar-drawer{transform:translateX(-100%);transition:transform .3s ease-in-out}
.sidebar-drawer.open{transform:translateX(0)}
.overlay{opacity:0;pointer-events:none;transition:opacity .3s}
.overlay.show{opacity:1;pointer-events:auto}
.word-span{transition:all .3s ease;border-radius:4px;padding:1px 2px}
.word-span.read{background:#dcfce7;color:#15803d;font-weight:700}
.word-span.current{background:#fef9c3}
.modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:200;align-items:center;justify-content:center}
.modal-bg.show{display:flex}
</style>
"""

# ═══════════════════════════════════════════════════════════
# STUDENT PAGE
# ═══════════════════════════════════════════════════════════
STUDENT_HTML = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>AI Speed Reader v{{ version }} — Learning Room</title>
{{ shared_css }}
</head>
<body class="bg-brand-graybg font-sans antialiased h-screen overflow-hidden flex">

<!-- Overlay sidebar mobile -->
<div id="overlay" class="overlay fixed inset-0 bg-slate-900/60 z-40" onclick="closeSidebar()"></div>

<!-- ═══ AUTH MODAL ═══ -->
<div id="authModal" class="modal-bg show">
  <div class="bg-white rounded-3xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
    <!-- Tabs -->
    <div class="flex border-b border-slate-100">
      <button id="tabLogin" onclick="switchTab('login')"
        class="flex-1 py-4 text-sm font-bold text-brand-blue border-b-2 border-brand-blue">
        Đăng nhập
      </button>
      <button id="tabRegister" onclick="switchTab('register')"
        class="flex-1 py-4 text-sm font-bold text-slate-400">
        Đăng ký mới
      </button>
    </div>
    <div class="p-8">
      <!-- Logo -->
      <div class="text-center mb-6">
        <div class="inline-flex items-center gap-3 mb-2">
          <div class="w-10 h-10 bg-brand-dark rounded-2xl flex items-center justify-center">
            <i class="fa-solid fa-bolt text-brand-emerald text-lg"></i>
          </div>
          <span class="text-2xl font-extrabold text-slate-900">SpeedAI</span>
        </div>
        <p class="text-xs text-slate-400">v{{ version }} — AI English Speed Reader</p>
      </div>

      <div id="authError" class="hidden mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600 font-medium"></div>

      <div class="space-y-4">
        <div>
          <label class="text-xs font-bold text-slate-500 uppercase tracking-wider block mb-1.5">Tên học viên</label>
          <div class="relative">
            <i class="fa-solid fa-user absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 text-sm"></i>
            <input id="authName" type="text" placeholder="Nhập tên của bạn..."
              class="w-full pl-11 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue/20">
          </div>
        </div>
        <div>
          <label class="text-xs font-bold text-slate-500 uppercase tracking-wider block mb-1.5">Mật khẩu</label>
          <div class="relative">
            <i class="fa-solid fa-lock absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 text-sm"></i>
            <input id="authPassword" type="password" placeholder="Tối thiểu 4 ký tự..."
              class="w-full pl-11 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue/20">
          </div>
        </div>
        <button id="authBtn" onclick="submitAuth()"
          class="w-full py-3.5 bg-brand-blue hover:bg-blue-600 text-white rounded-xl font-bold text-sm transition-all active:scale-[0.98] flex items-center justify-center gap-2">
          <i class="fa-solid fa-right-to-bracket"></i> <span id="authBtnText">Đăng nhập</span>
        </button>
        <p class="text-center text-xs text-slate-400" id="authToggleText">
          Chưa có tài khoản? <button onclick="switchTab('register')" class="text-brand-blue font-semibold">Đăng ký ngay</button>
        </p>
      </div>

      <div class="mt-5 pt-5 border-t border-slate-100 text-center">
        <p class="text-[11px] text-slate-400">Dữ liệu học tập của bạn được lưu an toàn trên cloud.</p>
      </div>
    </div>
  </div>
</div>

<!-- ═══ SIDEBAR ═══ -->
<aside id="sidebar"
  class="sidebar-drawer fixed lg:static top-0 left-0 bottom-0 w-[280px] bg-white border-r border-slate-200
         flex flex-col shrink-0 z-50 shadow-xl lg:shadow-sm lg:translate-x-0">
  <!-- Logo -->
  <div class="h-20 flex items-center justify-between px-6 border-b border-slate-100">
    <div class="flex items-center gap-3">
      <div class="w-9 h-9 bg-brand-dark rounded-xl flex items-center justify-center">
        <i class="fa-solid fa-bolt text-brand-emerald"></i>
      </div>
      <div>
        <div class="font-bold text-slate-900 leading-none">SpeedAI</div>
        <div class="text-[10px] text-slate-400 font-medium">v{{ version }}</div>
      </div>
    </div>
  </div>
  <!-- Profile -->
  <div class="px-6 py-5 border-b border-slate-100">
    <div class="flex items-center gap-3">
      <div class="w-12 h-12 rounded-full bg-gradient-to-br from-brand-blue to-brand-emerald flex items-center justify-center text-white font-extrabold text-lg" id="avatarInitial">?</div>
      <div>
        <div class="font-semibold text-slate-900 text-sm" id="sidebarName">Đang tải...</div>
        <div class="flex items-center gap-1.5 mt-0.5">
          <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-brand-blue text-[10px] font-bold border border-blue-100">
            <i class="fa-solid fa-gem text-[8px]"></i> Pro Reader
          </span>
        </div>
      </div>
    </div>
    <div class="mt-3 grid grid-cols-2 gap-2">
      <div class="bg-slate-50 rounded-xl p-2.5 text-center border border-slate-100">
        <div class="text-base font-extrabold text-slate-900" id="sidebarSessions">0</div>
        <div class="text-[10px] text-slate-400">Buổi học</div>
      </div>
      <div class="bg-slate-50 rounded-xl p-2.5 text-center border border-slate-100">
        <div class="text-base font-extrabold text-slate-900" id="sidebarBestWpm">--</div>
        <div class="text-[10px] text-slate-400">Best WPM</div>
      </div>
    </div>
  </div>
  <!-- Nav -->
  <nav class="flex-1 px-4 py-5 space-y-1 overflow-y-auto">
    <button onclick="showSection('learning');closeSidebar()"
      class="nav-btn w-full flex items-center gap-3 px-4 py-3 bg-brand-dark text-white rounded-xl shadow-sm relative text-left">
      <div class="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 bg-brand-emerald rounded-r-md"></div>
      <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-white/10 text-brand-emerald shrink-0">
        <i class="fa-solid fa-book-open-reader text-sm"></i>
      </div>
      <span class="font-medium text-sm ml-1">Learning Room</span>
    </button>
    <button onclick="showSection('library');closeSidebar()"
      class="nav-btn w-full flex items-center gap-3 px-4 py-3 text-slate-500 hover:bg-slate-50 rounded-xl transition-colors text-left">
      <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-100 shrink-0">
        <i class="fa-solid fa-newspaper text-sm"></i>
      </div>
      <span class="font-medium text-sm">Article Library</span>
    </button>
    <button onclick="showSection('metrics');closeSidebar()"
      class="nav-btn w-full flex items-center gap-3 px-4 py-3 text-slate-500 hover:bg-slate-50 rounded-xl transition-colors text-left">
      <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-100 shrink-0">
        <i class="fa-solid fa-chart-line text-sm"></i>
      </div>
      <span class="font-medium text-sm">Performance</span>
    </button>
    <button onclick="showSection('leaderboard');closeSidebar()"
      class="nav-btn w-full flex items-center gap-3 px-4 py-3 text-slate-500 hover:bg-slate-50 rounded-xl transition-colors text-left">
      <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-100 shrink-0">
        <i class="fa-solid fa-trophy text-sm"></i>
      </div>
      <span class="font-medium text-sm">Leaderboard</span>
    </button>
    <a href="/admin"
      class="flex items-center gap-3 px-4 py-3 text-slate-500 hover:bg-slate-50 rounded-xl transition-colors">
      <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-100 shrink-0">
        <i class="fa-solid fa-gear text-sm"></i>
      </div>
      <span class="font-medium text-sm">Admin Panel</span>
    </a>
  </nav>
  <!-- Logout + streak -->
  <div class="p-4 border-t border-slate-100 space-y-3">
    <div class="bg-slate-50 rounded-2xl p-3 border border-slate-100">
      <div class="flex items-center justify-between mb-1.5">
        <span class="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
          <i class="fa-solid fa-fire text-orange-400"></i> Daily Streak
        </span>
        <span class="text-xs font-bold text-brand-blue" id="streakCount">0 ngày</span>
      </div>
      <div class="w-full bg-slate-200 rounded-full h-1.5">
        <div class="bg-brand-blue h-1.5 rounded-full transition-all" id="streakBar" style="width:0%"></div>
      </div>
    </div>
    <button onclick="logout()"
      class="w-full flex items-center justify-center gap-2 py-2.5 bg-slate-100 hover:bg-red-50 hover:text-red-600 text-slate-500 rounded-xl text-xs font-bold transition-colors">
      <i class="fa-solid fa-right-from-bracket"></i> Đăng xuất
    </button>
  </div>
</aside>

<!-- ═══ MAIN ═══ -->
<main class="flex-1 flex flex-col min-w-0 overflow-hidden">
  <!-- Header -->
  <header class="h-16 lg:h-20 px-4 lg:px-8 flex items-center justify-between border-b border-slate-200 bg-white shrink-0">
    <div class="flex items-center gap-3">
      <button onclick="openSidebar()" class="lg:hidden w-10 h-10 flex items-center justify-center rounded-xl bg-slate-50 border border-slate-200 text-slate-600">
        <i class="fa-solid fa-bars-staggered"></i>
      </button>
      <div class="hidden md:block relative">
        <i class="fa-solid fa-magnifying-glass absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 text-sm"></i>
        <input id="searchInput" type="text" placeholder="Tìm bài báo..."
          class="pl-11 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm w-64 focus:outline-none focus:ring-2 focus:ring-brand-blue/20 placeholder:text-slate-400">
      </div>
    </div>
    <div class="flex items-center gap-2">
      <div class="text-right hidden sm:block">
        <div class="text-sm font-bold text-slate-900" id="headerName">--</div>
        <div class="text-[10px] text-slate-400" id="headerSub">Chưa đăng nhập</div>
      </div>
      <div class="w-9 h-9 rounded-full bg-gradient-to-br from-brand-blue to-brand-emerald flex items-center justify-center text-white font-bold text-sm" id="headerAvatar">?</div>
    </div>
  </header>

  <!-- Content -->
  <div class="flex-1 overflow-y-auto p-4 lg:p-8">
    <div class="max-w-[1400px] mx-auto space-y-6">

      <!-- ── LEARNING ROOM ── -->
      <div id="section-learning">
        <!-- Hero -->
        <section class="grid grid-cols-12 gap-5 mb-6">
          <div class="col-span-12 lg:col-span-7 bg-brand-dark rounded-3xl p-7 relative overflow-hidden flex flex-col justify-between min-h-[190px]">
            <div class="absolute top-0 right-0 w-64 h-64 bg-brand-blue/20 blur-[60px] rounded-full pointer-events-none"></div>
            <div class="relative z-10">
              <div class="flex items-center gap-2 text-brand-emerald text-xs font-bold tracking-widest uppercase mb-3">
                <i class="fa-solid fa-bolt"></i> Your Baseline
              </div>
              <div class="flex items-baseline gap-3">
                <span class="text-5xl lg:text-6xl font-extrabold text-white leading-none" id="heroWpm">--</span>
                <span class="text-2xl font-semibold text-slate-400">WPM</span>
                <span class="ml-2 px-2 py-0.5 bg-white/10 text-brand-emerald text-xs font-bold rounded-lg" id="heroRank">--</span>
              </div>
              <p class="text-slate-400 text-sm mt-2" id="heroSub">Chọn bài và bắt đầu luyện đọc</p>
            </div>
            <div class="relative z-10 flex items-center gap-3 mt-4">
              <div class="flex-1 bg-white/10 rounded-xl p-3">
                <div class="text-[10px] text-slate-400 mb-1">Độ chính xác</div>
                <div class="text-lg font-extrabold text-white"><span id="heroAcc">--</span>%</div>
              </div>
              <div class="flex-1 bg-white/10 rounded-xl p-3">
                <div class="text-[10px] text-slate-400 mb-1">Tổng buổi học</div>
                <div class="text-lg font-extrabold text-white" id="heroSessions">0</div>
              </div>
            </div>
          </div>
          <!-- Bar chart -->
          <div class="col-span-12 lg:col-span-5 bg-white rounded-3xl p-6 border border-slate-100 shadow-sm flex flex-col">
            <div class="flex items-center justify-between mb-1">
              <h3 class="font-semibold text-slate-900 text-sm">Word Retention Rate</h3>
              <span class="text-xs font-bold text-brand-emerald bg-emerald-50 px-2 py-0.5 rounded-md" id="retentionLabel">--</span>
            </div>
            <p class="text-xs text-slate-400 mb-3">7 buổi gần nhất</p>
            <div class="flex-1 flex items-end gap-2 pt-2" id="retentionBars"></div>
          </div>
        </section>

        <!-- Reading + Right panel -->
        <section class="grid grid-cols-12 gap-5 mb-6">
          <!-- Reading pane -->
          <div class="col-span-12 lg:col-span-8 bg-white rounded-3xl p-6 border border-slate-100 shadow-sm flex flex-col">
            <div class="flex items-start justify-between mb-4">
              <div>
                <div class="flex items-center gap-2 mb-1">
                  <span id="articleSource" class="text-[10px] font-bold text-white bg-red-500 px-2 py-0.5 rounded">--</span>
                  <span id="articleDiff" class="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">Easy</span>
                  <span id="articleTime" class="text-[10px] text-slate-400">-- min</span>
                </div>
                <h3 class="text-base lg:text-lg font-bold text-slate-900" id="articleTitle">Chọn bài báo bên dưới</h3>
              </div>
              <div class="flex items-center gap-2 text-slate-400 shrink-0 ml-2">
                <button onclick="cycleFontSize()" title="Cỡ chữ" class="hover:text-slate-700"><i class="fa-solid fa-font text-lg"></i></button>
                <button onclick="toggleFocus()" title="Focus" class="hover:text-slate-700"><i class="fa-solid fa-glasses text-lg"></i></button>
              </div>
            </div>
            <!-- Text -->
            <div id="readingPane" class="overflow-y-auto no-scrollbar" style="height:300px;">
              <p class="font-serif text-[20px] leading-[2.1] text-slate-400 text-base" id="readingText">
                Hãy chọn một bài báo từ danh sách bên dưới, sau đó nhấn nút microphone màu xanh để bắt đầu luyện đọc. Từ nào đọc đúng sẽ tự động chuyển màu xanh lá.
              </p>
            </div>
            <!-- Controls -->
            <div class="mt-5 flex items-center justify-center gap-5 pt-4 border-t border-slate-50">
              <button onclick="prevArticle()" class="w-12 h-12 rounded-full bg-slate-100 text-slate-500 hover:bg-slate-200 flex items-center justify-center transition-colors">
                <i class="fa-solid fa-backward-step"></i>
              </button>
              <button id="btnMic" onclick="toggleReading()"
                class="relative w-20 h-20 rounded-full bg-brand-blue text-white flex items-center justify-center shadow-lg shadow-blue-500/30 pulse-ring hover:bg-blue-600 transition-colors">
                <i class="fa-solid fa-microphone text-3xl" id="micIcon"></i>
              </button>
              <button onclick="nextArticle()" class="w-12 h-12 rounded-full bg-slate-100 text-slate-500 hover:bg-slate-200 flex items-center justify-center transition-colors">
                <i class="fa-solid fa-forward-step"></i>
              </button>
              <div class="pl-1">
                <p class="text-sm font-bold text-slate-900" id="micLabel">START READING</p>
                <p class="text-xs text-slate-400" id="micSub">Voice tracking active</p>
              </div>
            </div>
          </div>
          <!-- Right -->
          <div class="col-span-12 lg:col-span-4 space-y-4">
            <!-- Speed slider -->
            <div class="bg-white rounded-3xl p-5 border border-slate-100 shadow-sm">
              <div class="flex items-center justify-between mb-4">
                <h3 class="font-semibold text-slate-900 text-sm">Audio Speed</h3>
                <span class="text-xs font-bold text-brand-blue bg-blue-50 px-2 py-0.5 rounded-md" id="speedLabel">200 WPM</span>
              </div>
              <div class="relative h-8 mb-2">
                <div class="absolute top-1/2 -translate-y-1/2 left-0 right-0 h-1.5 bg-slate-100 rounded-full"></div>
                <div class="absolute top-1/2 -translate-y-1/2 left-0 h-1.5 bg-brand-emerald rounded-full" id="speedFill" style="width:14%"></div>
                <input type="range" min="100" max="800" value="200" step="10" id="speedSlider"
                  oninput="updateSpeed(this.value)"
                  class="absolute inset-0 w-full opacity-0 cursor-pointer">
                <div class="absolute top-1/2 -translate-y-1/2 w-5 h-5 bg-white border-2 border-brand-emerald rounded-full shadow-sm pointer-events-none" id="speedThumb" style="left:calc(14% - 10px)"></div>
              </div>
              <div class="flex justify-between text-[10px] text-slate-400 font-medium mb-4">
                <span>100</span><span>300</span><span>500</span><span>700</span><span>800</span>
              </div>
              <div class="flex items-center justify-center gap-[3px] h-8" id="waveform"></div>
            </div>
            <!-- Metrics -->
            <div class="grid grid-cols-3 gap-3">
              <div class="bg-white rounded-2xl p-4 border border-slate-100 shadow-sm flex flex-col">
                <div class="w-7 h-7 rounded-lg bg-slate-50 flex items-center justify-center text-slate-500 mb-2"><i class="fa-solid fa-gauge-high text-xs"></i></div>
                <p class="text-[10px] text-slate-400 mb-1">WPM</p>
                <p class="text-base font-bold text-slate-900" id="metricWpm">--</p>
                <div class="mt-auto pt-2 text-brand-emerald text-[10px] font-bold" id="metricWpmD">--</div>
              </div>
              <div class="bg-white rounded-2xl p-4 border border-slate-100 shadow-sm flex flex-col">
                <div class="w-7 h-7 rounded-lg bg-slate-50 flex items-center justify-center text-slate-500 mb-2"><i class="fa-solid fa-bullseye text-xs"></i></div>
                <p class="text-[10px] text-slate-400 mb-1">Accuracy</p>
                <p class="text-base font-bold text-slate-900"><span id="metricAcc">--</span>%</p>
                <div class="mt-auto pt-2 text-brand-emerald text-[10px] font-bold" id="metricAccD">--</div>
              </div>
              <div class="bg-white rounded-2xl p-4 border border-slate-100 shadow-sm flex flex-col items-center justify-center">
                <div class="w-12 h-12 rounded-full bg-emerald-50 flex items-center justify-center mb-1">
                  <span class="text-2xl font-extrabold text-brand-emerald" id="metricRank">--</span>
                </div>
                <p class="text-[10px] text-slate-400">Rank</p>
              </div>
            </div>
          </div>
        </section>

        <!-- Recommended -->
        <section>
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-xl font-bold text-slate-900">Recommended Articles</h2>
            <button onclick="showSection('library')" class="text-sm font-semibold text-brand-blue hover:underline">View all <i class="fa-solid fa-chevron-right text-xs ml-1"></i></button>
          </div>
          <div id="articleGrid" class="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="col-span-2 lg:col-span-4 text-center py-10 text-slate-400">
              <i class="fa-solid fa-spinner fa-spin text-2xl mb-2"></i>
              <p class="text-sm">Đang tải...</p>
            </div>
          </div>
        </section>
      </div>

      <!-- ── LIBRARY ── -->
      <div id="section-library" class="hidden">
        <div class="flex items-center justify-between mb-5">
          <h2 class="text-2xl font-bold text-slate-900">Article Library</h2>
          <span class="text-sm text-slate-400" id="libraryCount">0 bài</span>
        </div>
        <div id="libraryGrid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5"></div>
      </div>

      <!-- ── PERFORMANCE ── -->
      <div id="section-metrics" class="hidden">
        <h2 class="text-2xl font-bold text-slate-900 mb-5">Performance History</h2>
        <div id="metricsHistory" class="space-y-3">
          <div class="bg-white rounded-2xl p-8 border border-slate-100 text-center text-slate-400">
            <i class="fa-solid fa-chart-line text-4xl text-slate-200 mb-3"></i>
            <p>Chưa có dữ liệu. Hãy hoàn thành ít nhất 1 bài.</p>
          </div>
        </div>
      </div>

      <!-- ── LEADERBOARD ── -->
      <div id="section-leaderboard" class="hidden">
        <h2 class="text-2xl font-bold text-slate-900 mb-5">
          <i class="fa-solid fa-trophy text-yellow-400 mr-2"></i>Leaderboard
        </h2>
        <div class="bg-white rounded-3xl border border-slate-100 shadow-sm overflow-hidden">
          <div id="leaderboardBody" class="divide-y divide-slate-50">
            <div class="p-8 text-center text-slate-400"><i class="fa-solid fa-spinner fa-spin text-2xl mb-2"></i><p>Đang tải...</p></div>
          </div>
        </div>
      </div>

    </div>
  </div>

  <!-- Mobile bottom nav -->
  <nav class="lg:hidden fixed bottom-0 left-0 right-0 h-16 bg-white border-t border-slate-100 flex items-center justify-around px-2 z-30">
    <button onclick="showSection('learning')" class="bnav flex flex-col items-center gap-1 text-brand-blue px-3">
      <i class="fa-solid fa-house-chimney text-lg"></i><span class="text-[9px] font-bold uppercase">Home</span>
    </button>
    <button onclick="showSection('library')" class="bnav flex flex-col items-center gap-1 text-slate-400 px-3">
      <i class="fa-solid fa-book-open text-lg"></i><span class="text-[9px] font-bold uppercase">Library</span>
    </button>
    <button onclick="showSection('metrics')" class="bnav flex flex-col items-center gap-1 text-slate-400 px-3">
      <i class="fa-solid fa-chart-simple text-lg"></i><span class="text-[9px] font-bold uppercase">Stats</span>
    </button>
    <button onclick="showSection('leaderboard')" class="bnav flex flex-col items-center gap-1 text-slate-400 px-3">
      <i class="fa-solid fa-trophy text-lg"></i><span class="text-[9px] font-bold uppercase">Top</span>
    </button>
    <a href="/admin" class="flex flex-col items-center gap-1 text-slate-400 px-3">
      <i class="fa-solid fa-gear text-lg"></i><span class="text-[9px] font-bold uppercase">Admin</span>
    </a>
  </nav>
</main>

<div id="toast" class="fixed bottom-20 lg:bottom-6 left-1/2 -translate-x-1/2 bg-brand-dark text-white px-5 py-3 rounded-xl text-sm shadow-xl opacity-0 pointer-events-none transition-all z-[300] whitespace-nowrap"></div>

<script>
// ══════════════════════════════════════════════
// STATE
// ══════════════════════════════════════════════
const $  = id => document.getElementById(id);
let student    = null;   // {id, name, streak, total_sessions}
let articles   = [];
let selIdx     = -1;
let words      = [];
let matchIdx   = 0, spokenCount = 0, correctCount = 0;
let startTime  = null;
let recognition = null;
let isListening = false;
let fontSize   = 20;
let authMode   = 'login';  // 'login' | 'register'
let myScores   = [];

function showToast(msg, dur=2800) {
  const t = $('toast');
  t.textContent = msg; t.style.opacity = '1';
  setTimeout(() => t.style.opacity = '0', dur);
}

// ══ Sidebar ══
function openSidebar()  { $('sidebar').classList.add('open'); $('overlay').classList.add('show'); }
function closeSidebar() { $('sidebar').classList.remove('open'); $('overlay').classList.remove('show'); }

// ══ Section nav ══
const SECTIONS = ['learning','library','metrics','leaderboard'];
function showSection(name) {
  SECTIONS.forEach(s => $('section-'+s)?.classList.toggle('hidden', s!==name));
  document.querySelectorAll('.nav-btn').forEach(b => {
    b.classList.remove('bg-brand-dark','text-white','shadow-sm');
    b.classList.add('text-slate-500','hover:bg-slate-50');
  });
  document.querySelectorAll('.bnav').forEach((b,i) => {
    b.classList.toggle('text-brand-blue', SECTIONS[i]===name);
    b.classList.toggle('text-slate-400',  SECTIONS[i]!==name);
  });
  if (name === 'library')     renderLibrary();
  if (name === 'metrics')     renderMetrics();
  if (name === 'leaderboard') loadLeaderboard();
}

// ══ AUTH ══
function switchTab(mode) {
  authMode = mode;
  const isLogin = mode === 'login';
  $('tabLogin').className    = 'flex-1 py-4 text-sm font-bold ' + (isLogin ? 'text-brand-blue border-b-2 border-brand-blue' : 'text-slate-400');
  $('tabRegister').className = 'flex-1 py-4 text-sm font-bold ' + (!isLogin ? 'text-brand-blue border-b-2 border-brand-blue' : 'text-slate-400');
  $('authBtnText').textContent  = isLogin ? 'Đăng nhập' : 'Tạo tài khoản';
  $('authToggleText').innerHTML = isLogin
    ? 'Chưa có tài khoản? <button onclick="switchTab(\'register\')" class="text-brand-blue font-semibold">Đăng ký ngay</button>'
    : 'Đã có tài khoản? <button onclick="switchTab(\'login\')" class="text-brand-blue font-semibold">Đăng nhập</button>';
  $('authError').classList.add('hidden');
}

async function submitAuth() {
  const name = $('authName').value.trim();
  const pw   = $('authPassword').value.trim();
  $('authError').classList.add('hidden');
  if (!name || !pw) { showAuthError('Vui lòng nhập đầy đủ thông tin.'); return; }
  const btn = $('authBtn');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Đang xử lý...';
  try {
    const url = authMode === 'login' ? '/api/auth/login' : '/api/auth/register';
    const res = await fetch(url, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,password:pw})});
    const data = await res.json();
    if (data.success) {
      student = data.student;
      $('authModal').classList.remove('show');
      initUI();
      loadArticles();
      loadMyScores();
      showToast('👋 Chào mừng, ' + student.name + '!');
    } else {
      showAuthError(data.error || 'Có lỗi xảy ra');
    }
  } catch(e) { showAuthError('Không thể kết nối server.'); }
  finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-right-to-bracket"></i> <span id="authBtnText">' + (authMode==='login'?'Đăng nhập':'Tạo tài khoản') + '</span>';
  }
}

function showAuthError(msg) {
  $('authError').textContent = msg;
  $('authError').classList.remove('hidden');
}

// Enter key để submit auth
['authName','authPassword'].forEach(id => {
  $( id )?.addEventListener('keydown', e => { if(e.key==='Enter') submitAuth(); });
});

function initUI() {
  if (!student) return;
  const initial = (student.name||'?')[0].toUpperCase();
  $('avatarInitial').textContent = initial;
  $('headerAvatar').textContent  = initial;
  $('sidebarName').textContent   = student.name;
  $('headerName').textContent    = student.name;
  $('headerSub').textContent     = 'Pro Reader';
  $('sidebarSessions').textContent = student.total_sessions || 0;
  $('heroSessions').textContent    = student.total_sessions || 0;
  const streak = student.streak || 0;
  $('streakCount').textContent = streak + ' ngày';
  $('streakBar').style.width   = Math.min(100, (streak%7)/7*100) + '%';
}

async function logout() {
  await fetch('/api/auth/logout', {method:'POST'});
  student = null; articles = []; myScores = [];
  $('authModal').classList.add('show');
  $('authPassword').value = '';
  $('authError').classList.add('hidden');
}

// ══ Articles ══
function srcBg(s) {
  const m = {'BBC Tech':'bg-red-500','BBC World':'bg-red-500','BBC Science':'bg-red-500','BBC Business':'bg-red-500',
    'CNN':'bg-red-600','CNN Tech':'bg-red-600',
    'Reuters World':'bg-slate-700','Reuters Tech':'bg-slate-700','Reuters Biz':'bg-slate-700',
    'AP Top':'bg-orange-600','AP World':'bg-orange-600','AP Tech':'bg-orange-600',
    'NPR':'bg-blue-700','NPR World':'bg-blue-700',
    'Guardian World':'bg-blue-900','Guardian Tech':'bg-blue-900',
    'Al Jazeera':'bg-yellow-600','NASA':'bg-indigo-700',
    'Science Daily':'bg-teal-600','Ars Technica':'bg-orange-700',
    'BBC':'bg-red-500','NatGeo':'bg-blue-600','AP':'bg-orange-600','Reuters':'bg-slate-700'};
  return m[s] || 'bg-slate-700';
}
function diffColor(d) { return ({Easy:'emerald',Medium:'yellow',Hard:'amber'})[d] || 'emerald'; }

function articleCard(a, idx, large=false) {
  const sb = srcBg(a.source||'');
  const dc = diffColor(a.difficulty||'Easy');
  return `
  <article onclick="selectArticle(${idx})"
    class="bg-white rounded-3xl border border-slate-100 shadow-sm overflow-hidden cursor-pointer
           hover:shadow-md hover:-translate-y-1 transition-all group
           ${selIdx===idx?'ring-2 ring-brand-blue shadow-md':''}" data-idx="${idx}">
    <div class="relative ${large?'h-44':'h-36'} overflow-hidden">
      <img src="${a.image||'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&q=70'}"
           alt="${a.title}"
           class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
           onerror="this.src='https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&q=70'">
      <span class="absolute top-3 left-3 text-[10px] font-bold text-white ${sb} px-2 py-0.5 rounded">${a.source||'--'}</span>
    </div>
    <div class="p-4">
      <div class="flex items-center gap-2 mb-2">
        <span class="text-[10px] font-semibold text-${dc}-700 bg-${dc}-50 px-2 py-0.5 rounded">${a.difficulty||'Easy'}</span>
        <span class="text-[10px] text-slate-400">${a.read_time||'5'} min</span>
        ${a.published ? `<span class="text-[10px] text-slate-400"><i class="fa-solid fa-calendar mr-0.5"></i>${a.published}</span>` : ''}
      </div>
      <h4 class="text-sm font-bold text-slate-900 leading-snug mb-1 ${large?'':'line-clamp-2'}">${a.title||''}</h4>
      <p class="text-xs text-slate-400 line-clamp-1">${(a.content||'').slice(0,70)}...</p>
    </div>
  </article>`;
}

async function loadArticles() {
  try {
    const res = await fetch('/api/articles');
    const data = await res.json();
    articles = data.articles || [];
  } catch(e) { articles = []; }
  renderArticleGrid();
}

function renderArticleGrid() {
  if (!articles.length) {
    $('articleGrid').innerHTML = '<div class="col-span-4 text-center py-10 text-slate-400"><i class="fa-solid fa-newspaper text-2xl mb-2"></i><p class="text-sm">Chưa có bài. Admin hãy quét và duyệt bài.</p></div>';
    return;
  }
  $('articleGrid').innerHTML = articles.slice(0,4).map((a,i) => articleCard(a,i)).join('');
}

function renderLibrary() {
  if (!articles.length) { $('libraryGrid').innerHTML = '<div class="text-slate-400 text-center py-10 col-span-3">Chưa có bài báo</div>'; return; }
  $('libraryCount').textContent = articles.length + ' bài';
  $('libraryGrid').innerHTML = articles.map((a,i) => articleCard(a,i,true)).join('');
}

function selectArticle(idx) {
  selIdx = idx;
  const a = articles[idx];
  $('articleSource').textContent = a.source||'--';
  $('articleDiff').textContent   = a.difficulty||'Easy';
  $('articleTime').textContent   = (a.read_time||'5') + ' min';
  $('articleTitle').textContent  = a.title||'';
  buildWords(a.content||'');
  showSection('learning');
  renderArticleGrid();
  setTimeout(() => document.querySelector('section.grid.grid-cols-12 + section')
    ?.scrollIntoView({behavior:'smooth',block:'start'}), 100);
  showToast('📖 ' + (a.title||'').slice(0,50));
}

function prevArticle() { if(articles.length) selectArticle((selIdx<=0?articles.length:selIdx)-1); }
function nextArticle() { if(articles.length) selectArticle((selIdx+1)%articles.length); }

// ══ Reading ══
function norm(w) { return (w||'').toLowerCase().replace(/[^a-z0-9']/g,''); }

function buildWords(content) {
  const raw = content.trim().split(/\s+/);
  words = raw.map(w => ({display:w, clean:norm(w)})).filter(w=>w.clean);
  matchIdx=0; spokenCount=0; correctCount=0;
  $('readingText').innerHTML = words.map((w,i) =>
    `<span class="word-span" id="ws-${i}">${w.display} </span>`).join('');
  $('ws-0')?.classList.add('current');
}

function markWord(i) {
  const el = $('ws-'+i); if(!el) return;
  el.classList.remove('current'); el.classList.add('read');
  el.scrollIntoView({behavior:'smooth',block:'center'});
  $('ws-'+(i+1))?.classList.add('current');
}

function toggleReading() {
  if (!student) { showToast('⚠️ Vui lòng đăng nhập!'); return; }
  if (selIdx < 0) { showToast('⚠️ Hãy chọn bài báo trước!'); return; }
  if (isListening) stopReading(); else startReading();
}

function startReading() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { showToast('❌ Cần dùng Chrome để nhận diện giọng nói.'); return; }
  recognition = new SR();
  recognition.lang = 'en-US';
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.onresult = e => {
    let t = '';
    for(let i=e.resultIndex;i<e.results.length;i++) t += ' '+e.results[i][0].transcript;
    t.trim().split(/\s+/).map(norm).filter(Boolean).forEach(sw => {
      if(matchIdx>=words.length) return;
      spokenCount++;
      if(sw===words[matchIdx].clean){correctCount++;markWord(matchIdx);matchIdx++;}
    });
    if(matchIdx>=words.length) finishReading();
  };
  recognition.onerror = ()=>{};
  recognition.onend = ()=>{ isListening=false; micUI(false); };
  recognition.start();
  isListening=true; startTime=performance.now();
  micUI(true); waveformUI(true);
}

function stopReading() { try{recognition?.stop();}catch(e){} finishReading(); }

function finishReading() {
  try{recognition?.stop();}catch(e){}
  isListening=false; micUI(false); waveformUI(false);
  if(!startTime) return;
  const min  = Math.max((performance.now()-startTime)/60000, 0.05);
  const wpm  = Math.round(matchIdx/min);
  const acc  = spokenCount>0 ? Math.round(correctCount/spokenCount*100) : 0;
  const rank = calcRank(wpm,acc);
  startTime  = null;

  // Update UI
  $('metricWpm').textContent = wpm;
  $('metricAcc').textContent = acc;
  $('metricRank').textContent = rank;
  $('metricWpmD').textContent = '+'+wpm+' WPM';
  $('metricAccD').textContent = '+'+acc+'%';
  $('heroWpm').textContent  = wpm;
  $('heroAcc').textContent  = acc;
  $('heroRank').textContent = rank;
  $('heroSub').textContent  = `Đọc ${matchIdx} từ • ${acc}% chính xác`;

  // Save
  const scoreRec = { wpm, accuracy:acc, rank, words_read:matchIdx,
    article_title: articles[selIdx]?.title||'', article_id: articles[selIdx]?.id||'' };
  saveScore(scoreRec);
  showToast(`✅ ${wpm} WPM | ${acc}% | Rank ${rank}`, 3500);
}

function calcRank(wpm,acc) {
  if(acc>=95&&wpm>=130) return 'S';
  if(acc>=90&&wpm>=100) return 'A';
  if(acc>=80&&wpm>=70)  return 'B';
  return 'C';
}

async function saveScore(rec) {
  try {
    const res = await fetch('/api/save_score',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(rec)});
    const data = await res.json();
    if(data.success) {
      myScores.unshift({...rec, created_at:new Date().toISOString(), student_name:student?.name});
      if(student) { student.total_sessions = (student.total_sessions||0)+1; $('heroSessions').textContent=student.total_sessions; }
      renderRetentionBars();
      renderMetrics();
    }
  } catch(e){}
}

async function loadMyScores() {
  try {
    const res = await fetch('/api/student/scores');
    const data = await res.json();
    if(data.success) {
      myScores = data.scores||[];
      if(myScores.length) {
        const last = myScores[0];
        $('heroWpm').textContent = last.wpm;
        $('heroAcc').textContent = last.accuracy;
        $('heroRank').textContent= last.rank;
        $('metricWpm').textContent = last.wpm;
        $('metricAcc').textContent = last.accuracy;
        $('metricRank').textContent= last.rank;
      }
      $('sidebarBestWpm').textContent = myScores.length ? Math.max(...myScores.map(s=>s.wpm)) : '--';
      renderRetentionBars(); renderMetrics();
    }
  } catch(e){}
}

function renderRetentionBars() {
  const days=['M','T','W','T','F','S','S'];
  const vals = myScores.slice(0,7).reverse().map(s=>s.accuracy);
  while(vals.length<7) vals.push(0);
  const max = Math.max(...vals, 1);
  const best = myScores.length ? myScores[0].accuracy : 0;
  $('retentionLabel').textContent = best ? '+'+best+'%' : '--';
  $('retentionBars').innerHTML = days.map((d,i) => {
    const h = Math.round(vals[i]/max*100);
    const col = h>=80 ? 'bg-brand-blue' : (h>=50?'bg-brand-emerald':'bg-slate-100');
    return `<div class="flex-1 flex flex-col items-center gap-1">
      <div class="w-full ${col} rounded-t-md" style="height:${Math.max(h,4)}%"></div>
      <span class="text-[10px] text-slate-400">${d}</span>
    </div>`;
  }).join('');
}

function renderMetrics() {
  if(!myScores.length) return;
  $('metricsHistory').innerHTML = myScores.slice(0,15).map((h,i) => {
    const rankColors = {S:'text-brand-emerald bg-emerald-50',A:'text-blue-500 bg-blue-50',B:'text-yellow-500 bg-yellow-50',C:'text-red-400 bg-red-50'};
    const rc = rankColors[h.rank||'C'] || rankColors['C'];
    return `<div class="bg-white rounded-2xl p-4 border border-slate-100 shadow-sm flex items-center gap-4">
      <div class="w-12 h-12 rounded-full ${rc.split(' ')[1]} flex items-center justify-center shrink-0">
        <span class="text-xl font-extrabold ${rc.split(' ')[0]}">${h.rank||'C'}</span>
      </div>
      <div class="flex-1 min-w-0">
        <p class="font-semibold text-slate-900 text-sm truncate">${h.article_title||'Bài luyện tập'}</p>
        <p class="text-xs text-slate-400 mt-0.5">${new Date(h.created_at).toLocaleString('vi-VN')}</p>
      </div>
      <div class="text-right shrink-0">
        <p class="text-lg font-extrabold text-slate-900">${h.wpm} <span class="text-xs text-slate-400 font-normal">WPM</span></p>
        <p class="text-xs font-bold ${h.accuracy>=90?'text-brand-emerald':'text-slate-500'}">${h.accuracy}%</p>
      </div>
    </div>`;
  }).join('');
}

async function loadLeaderboard() {
  $('leaderboardBody').innerHTML = '<div class="p-8 text-center text-slate-400"><i class="fa-solid fa-spinner fa-spin text-2xl mb-2"></i><p>Đang tải...</p></div>';
  try {
    const res = await fetch('/api/leaderboard');
    const data = await res.json();
    const board = data.leaderboard||[];
    if(!board.length) { $('leaderboardBody').innerHTML='<div class="p-8 text-center text-slate-400">Chưa có dữ liệu</div>'; return; }
    const medals = ['🥇','🥈','🥉'];
    $('leaderboardBody').innerHTML = board.map((r,i) => `
      <div class="flex items-center gap-4 px-6 py-4 ${r.student_name===student?.name?'bg-blue-50':''}">
        <div class="w-8 text-center font-extrabold text-lg ${i<3?'':'text-slate-400'}">${medals[i]||('#'+(i+1))}</div>
        <div class="w-10 h-10 rounded-full bg-gradient-to-br from-brand-blue to-brand-emerald flex items-center justify-center text-white font-bold shrink-0">
          ${(r.student_name||'?')[0].toUpperCase()}
        </div>
        <div class="flex-1 min-w-0">
          <p class="font-bold text-slate-900 text-sm">${r.student_name} ${r.student_name===student?.name?'<span class="text-[10px] text-brand-blue font-semibold">(bạn)</span>':''}</p>
          <p class="text-xs text-slate-400">${r.total_sessions} buổi học</p>
        </div>
        <div class="text-right">
          <p class="font-extrabold text-slate-900">${r.best_wpm} WPM</p>
          <p class="text-xs font-bold text-brand-emerald">${r.avg_accuracy}% avg</p>
        </div>
        <div class="w-8 h-8 rounded-full ${({'S':'bg-emerald-50 text-brand-emerald','A':'bg-blue-50 text-blue-500','B':'bg-yellow-50 text-yellow-500','C':'bg-red-50 text-red-400'})[r.best_rank||'C']} flex items-center justify-center font-extrabold text-sm">${r.best_rank||'C'}</div>
      </div>`).join('');
  } catch(e) { $('leaderboardBody').innerHTML='<div class="p-8 text-center text-red-400">Lỗi tải dữ liệu</div>'; }
}

// ══ Audio speed ══
function updateSpeed(val) {
  const p = (val-100)/700*100;
  $('speedLabel').textContent = val+' WPM';
  $('speedFill').style.width = p+'%';
  $('speedThumb').style.left = 'calc('+p+'% - 10px)';
}

// ══ Font & Focus ══
function cycleFontSize() {
  const sizes=[18,20,22,24,26];
  fontSize = sizes[(sizes.indexOf(fontSize)+1)%sizes.length];
  $('readingText').style.fontSize = fontSize+'px';
}
let focusMode=false;
function toggleFocus() { focusMode=!focusMode; $('readingPane').style.height=focusMode?'500px':'300px'; }

// ══ Mic UI ══
function micUI(active) {
  const btn=$('btnMic');
  if(active) {
    btn.classList.replace('bg-brand-blue','bg-red-500');
    $('micIcon').className='fa-solid fa-stop text-3xl';
    $('micLabel').textContent='STOP READING';
    $('micSub').textContent='Đang nghe... đọc to!';
  } else {
    btn.classList.replace('bg-red-500','bg-brand-blue');
    $('micIcon').className='fa-solid fa-microphone text-3xl';
    $('micLabel').textContent='START READING';
    $('micSub').textContent='Voice tracking active';
  }
}

// ══ Waveform ══
function waveformUI(active=false) {
  const hs=[30,60,40,80,100,70,50,35,55,25];
  $('waveform').innerHTML=hs.map((h,i)=>`<span class="w-1 rounded-full wave-bar ${active&&i>2&&i<7?'bg-brand-emerald':'bg-slate-200'}" style="height:${h}%;animation-delay:${i*.1}s"></span>`).join('');
}

// ══ Check session on load ══
async function checkSession() {
  try {
    const res = await fetch('/api/auth/me');
    const data = await res.json();
    if(data.logged_in) {
      student = data.student;
      $('authModal').classList.remove('show');
      initUI(); loadArticles(); loadMyScores();
    }
  } catch(e) {}
}

// ══ INIT ══
waveformUI(false);
renderRetentionBars();
updateSpeed(200);
checkSession();
</script>
</body></html>"""

# ═══════════════════════════════════════════════════════════
# ADMIN PAGE
# ═══════════════════════════════════════════════════════════
ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>AI Speed Reader v{{ version }} — Admin</title>
{{ shared_css }}
</head>
<body class="bg-brand-graybg font-sans antialiased h-screen overflow-hidden flex">
<div id="overlay" class="overlay fixed inset-0 bg-slate-900/60 z-40" onclick="closeSidebar()"></div>

<!-- Sidebar -->
<aside id="sidebar" class="sidebar-drawer fixed lg:static top-0 left-0 bottom-0 w-[280px] bg-brand-dark flex flex-col shrink-0 z-50 shadow-xl">
  <div class="h-20 flex items-center px-6 border-b border-white/10">
    <div class="flex items-center gap-3">
      <div class="w-9 h-9 bg-brand-emerald rounded-xl flex items-center justify-center"><i class="fa-solid fa-bolt text-white"></i></div>
      <div>
        <div class="font-bold text-white">SpeedAI Admin</div>
        <div class="text-[10px] text-slate-500">v{{ version }}</div>
      </div>
    </div>
  </div>
  <nav class="flex-1 px-4 py-6 space-y-1 overflow-y-auto">
    <div class="px-4 mb-3 text-[10px] font-bold text-slate-500 uppercase tracking-widest">Menu</div>
    <a href="#" class="flex items-center gap-3 px-4 py-3 text-slate-400 hover:bg-white/5 hover:text-white rounded-xl transition-colors">
      <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-white/5"><i class="fa-solid fa-chart-pie text-sm"></i></div>
      <span class="text-sm font-medium">Overview</span>
    </a>
    <a href="#" class="flex items-center gap-3 px-4 py-3 bg-brand-blue text-white rounded-xl">
      <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-white/20"><i class="fa-solid fa-spider text-sm"></i></div>
      <span class="text-sm font-medium ml-1">Content Crawler</span>
    </a>
    <a href="#" class="flex items-center gap-3 px-4 py-3 text-slate-400 hover:bg-white/5 hover:text-white rounded-xl transition-colors">
      <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-white/5"><i class="fa-solid fa-users text-sm"></i></div>
      <span class="text-sm font-medium">Users</span>
    </a>
    <div class="px-4 mt-6 mb-3 text-[10px] font-bold text-slate-500 uppercase tracking-widest">System</div>
    <a href="#" class="flex items-center gap-3 px-4 py-3 text-slate-400 hover:bg-white/5 hover:text-white rounded-xl transition-colors">
      <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-white/5"><i class="fa-solid fa-robot text-sm"></i></div>
      <span class="text-sm font-medium">AI Engine</span>
    </a>
  </nav>
  <div class="p-4 border-t border-white/10">
    <div class="flex items-center gap-3 px-2">
      <img src="https://storage.googleapis.com/uxpilot-auth.appspot.com/avatars/avatar-4.jpg" class="w-10 h-10 rounded-full border border-white/20" alt="">
      <div><p class="text-xs font-bold text-white">System Admin</p><p class="text-[10px] text-slate-500">Master Control</p></div>
    </div>
  </div>
</aside>

<!-- Main -->
<main class="flex-1 flex flex-col min-w-0 overflow-hidden">
  <header class="h-16 lg:h-20 px-4 lg:px-8 flex items-center justify-between border-b border-slate-200 bg-white shrink-0">
    <div class="flex items-center gap-3">
      <button onclick="openSidebar()" class="lg:hidden w-10 h-10 flex items-center justify-center rounded-xl bg-slate-50 border border-slate-200 text-slate-600"><i class="fa-solid fa-bars-staggered"></i></button>
      <div>
        <h1 class="text-base lg:text-lg font-bold text-slate-900">Content Crawler Controller</h1>
        <p class="text-xs text-slate-500 hidden md:block">Manage news ingestion and article approval queue</p>
      </div>
    </div>
    <div class="flex items-center gap-3">
      <div class="flex items-center gap-2 px-3 py-1.5 bg-emerald-50 text-brand-emerald rounded-lg border border-emerald-100">
        <span class="w-1.5 h-1.5 bg-brand-emerald rounded-full animate-pulse"></span>
        <span class="text-[10px] font-bold uppercase tracking-wider hidden sm:block">Crawler Online</span>
      </div>
      <a href="/" class="flex items-center gap-2 px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100 transition-colors">
        <i class="fa-solid fa-arrow-left"></i> Student View
      </a>
    </div>
  </header>

  <div class="flex-1 overflow-y-auto p-4 lg:p-8">
    <div class="max-w-[1100px] mx-auto space-y-7">

      <!-- Published articles -->
      <section class="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
        <div class="flex items-center justify-between mb-4">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl bg-emerald-50 text-brand-emerald flex items-center justify-center"><i class="fa-solid fa-newspaper text-sm"></i></div>
            <h2 class="text-base font-bold text-slate-900">Bài đã duyệt</h2>
            <span id="pubBadge" class="px-2 py-0.5 bg-brand-emerald text-white rounded-full text-xs font-bold">0</span>
          </div>
          <button onclick="loadPublished()" class="text-xs font-semibold text-brand-blue hover:underline flex items-center gap-1">
            <i class="fa-solid fa-rotate-right"></i> Refresh
          </button>
        </div>
        <div id="pubList" class="space-y-2 max-h-60 overflow-y-auto no-scrollbar">
          <p class="text-center text-slate-400 text-sm py-4">Đang tải...</p>
        </div>
      </section>

      <!-- Source config -->
      <section class="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
        <div class="flex items-center gap-3 mb-5">
          <div class="w-9 h-9 rounded-xl bg-blue-50 text-brand-blue flex items-center justify-center"><i class="fa-solid fa-filter text-sm"></i></div>
          <h2 class="text-base font-bold text-slate-900">Source Configuration</h2>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div class="space-y-1.5">
            <label class="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Target News Agency</label>
            <div class="relative">
              <select id="selSource" class="w-full pl-4 pr-10 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm appearance-none focus:outline-none focus:ring-2 focus:ring-brand-blue/20">
                <option>BBC News (Global)</option><option>BBC World</option>
                <option>CNN International</option><option>Reuters Technology</option>
                <option>AP News</option><option>All Sources</option>
              </select>
              <i class="fa-solid fa-chevron-down absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 text-xs pointer-events-none"></i>
            </div>
          </div>
          <div class="space-y-1.5">
            <label class="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Content Category</label>
            <div class="relative">
              <select id="selCat" class="w-full pl-4 pr-10 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm appearance-none focus:outline-none focus:ring-2 focus:ring-brand-blue/20">
                <option>Technology & AI</option><option>Science & Nature</option>
                <option>Business & Finance</option><option>World Politics</option><option>All Topics</option>
              </select>
              <i class="fa-solid fa-chevron-down absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 text-xs pointer-events-none"></i>
            </div>
          </div>
          <div class="flex items-end">
            <button id="btnCrawl" onclick="runCrawler()"
              class="w-full py-3 bg-brand-blue hover:bg-blue-600 text-white rounded-xl text-sm font-bold shadow-lg shadow-brand-blue/20 transition-all active:scale-[0.98] flex items-center justify-center gap-2">
              <i class="fa-solid fa-play text-xs"></i> RUN CRAWLER / SCAN NEWS
            </button>
          </div>
        </div>
      </section>

      <!-- Queue -->
      <section class="space-y-4">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <h2 class="text-xl font-bold text-slate-900">Pending Article Queue</h2>
            <span id="queueBadge" class="px-2.5 py-0.5 bg-slate-200 text-slate-600 rounded-full text-xs font-bold">0</span>
          </div>
          <div class="flex gap-2">
            <button onclick="selectAll()" class="px-4 py-2 bg-white border border-slate-200 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-50">Select All</button>
            <button onclick="batchApprove()" class="px-4 py-2 bg-brand-emerald text-white rounded-xl text-xs font-bold hover:bg-emerald-600">Batch Approve</button>
          </div>
        </div>
        <div id="queueList" class="space-y-4">
          <div class="bg-white rounded-2xl p-8 border border-slate-200 text-center text-slate-400">
            <i class="fa-solid fa-spider text-4xl text-slate-200 mb-3"></i>
            <p class="font-medium">Nhấn "RUN CRAWLER" để quét tin tức mới.</p>
          </div>
        </div>
      </section>
    </div>
  </div>
</main>

<div id="toast" class="fixed bottom-6 left-1/2 -translate-x-1/2 bg-brand-dark text-white px-5 py-3 rounded-xl text-sm shadow-xl opacity-0 pointer-events-none transition-all z-[100] whitespace-nowrap"></div>

<script>
const $ = id => document.getElementById(id);
function openSidebar()  { $('sidebar').classList.add('open'); $('overlay').classList.add('show'); }
function closeSidebar() { $('sidebar').classList.remove('open'); $('overlay').classList.remove('show'); }
function showToast(msg) { const t=$('toast'); t.textContent=msg; t.style.opacity='1'; setTimeout(()=>t.style.opacity='0',2800); }
function esc(s) { const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }

let crawled = [];
let selected = new Set();

function srcBg(s) {
  const m = {'BBC Tech':'bg-red-500','BBC World':'bg-red-500','BBC Science':'bg-red-500','BBC Business':'bg-red-500',
    'CNN':'bg-red-600','CNN Tech':'bg-red-600',
    'Reuters World':'bg-slate-700','Reuters Tech':'bg-slate-700','Reuters Biz':'bg-slate-700',
    'AP Top':'bg-orange-600','AP World':'bg-orange-600','AP Tech':'bg-orange-600',
    'NPR':'bg-blue-700','NPR World':'bg-blue-700',
    'Guardian World':'bg-blue-900','Guardian Tech':'bg-blue-900',
    'Al Jazeera':'bg-yellow-600','NASA':'bg-indigo-700',
    'Science Daily':'bg-teal-600','Ars Technica':'bg-orange-700',
    'BBC':'bg-red-500','AP':'bg-orange-600','Reuters':'bg-slate-700'};
  return m[s] || 'bg-slate-700';
}
function diffBadge(d) { return ({Easy:'text-emerald-700 bg-emerald-50',Medium:'text-yellow-700 bg-yellow-50',Hard:'text-amber-700 bg-amber-50'})[d]||'text-emerald-700 bg-emerald-50'; }

// ── Published articles ──
async function loadPublished() {
  $('pubList').innerHTML = '<p class="text-center text-slate-400 text-sm py-4"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Đang tải...</p>';
  try {
    const res  = await fetch('/api/articles');
    const data = await res.json();
    const arts = data.articles||[];
    $('pubBadge').textContent = arts.length;
    if(!arts.length) { $('pubList').innerHTML='<p class="text-center text-slate-400 text-sm py-4">Chưa có bài nào được duyệt.</p>'; return; }
    $('pubList').innerHTML = arts.map(a => `
      <div class="flex items-center gap-3 px-3 py-2.5 bg-slate-50 rounded-xl border border-slate-100">
        <span class="text-[10px] font-bold text-white ${srcBg(a.source||'')} px-2 py-0.5 rounded shrink-0">${esc(a.source||'--')}</span>
        <span class="text-[10px] font-semibold ${diffBadge(a.difficulty||'Easy')} px-2 py-0.5 rounded shrink-0">${a.difficulty||'Easy'}</span>
        <p class="flex-1 text-sm font-medium text-slate-900 truncate">${esc(a.title||'')}</p>
        <span class="text-[10px] text-slate-400 shrink-0">${a.read_time||'5'}min</span>
        ${a.id && !String(a.id).startsWith('d') ? `<button onclick="deleteArticle(${a.id})" title="Xoá" class="text-slate-400 hover:text-red-500 transition-colors shrink-0"><i class="fa-solid fa-trash text-xs"></i></button>` : ''}
      </div>`).join('');
  } catch(e) { $('pubList').innerHTML='<p class="text-center text-red-400 text-sm py-4">Lỗi tải dữ liệu.</p>'; }
}

async function deleteArticle(id) {
  if(!confirm('Xoá bài này?')) return;
  try {
    const res = await fetch('/api/articles/delete/'+id, {method:'DELETE'});
    const d = await res.json();
    if(d.success) { showToast('🗑️ Đã xoá bài báo'); loadPublished(); }
    else showToast('❌ Lỗi: ' + (d.error||''));
  } catch(e) { showToast('❌ Lỗi kết nối'); }
}

// ── Crawler ──
async function runCrawler() {
  const btn=$('btnCrawl');
  btn.disabled=true;
  btn.innerHTML='<i class="fa-solid fa-circle-notch fa-spin text-xs"></i> Đang quét...';
  $('queueList').innerHTML='<div class="bg-white rounded-2xl p-8 border text-center text-slate-400"><i class="fa-solid fa-circle-notch fa-spin text-3xl mb-3"></i><p>Đang tải RSS feeds...</p></div>';
  selected.clear();
  try {
    const res = await fetch('/api/crawl',{method:'POST'});
    const data = await res.json();
    crawled = data.articles||[];
    $('queueBadge').textContent = crawled.length;
    renderQueue();
    showToast('✅ Quét xong ' + crawled.length + ' bài');
  } catch(e) {
    $('queueList').innerHTML='<div class="bg-white rounded-2xl p-8 border text-center text-red-400"><i class="fa-solid fa-triangle-exclamation text-3xl mb-3"></i><p>Lỗi kết nối. Vui lòng thử lại.</p></div>';
  } finally {
    btn.disabled=false;
    btn.innerHTML='<i class="fa-solid fa-play text-xs"></i> RUN CRAWLER / SCAN NEWS';
  }
}

function renderQueue() {
  if(!crawled.length) { $('queueList').innerHTML='<div class="bg-white rounded-2xl p-8 border text-center text-slate-400">Không tìm thấy bài phù hợp.</div>'; return; }
  $('queueList').innerHTML = crawled.map((a,idx) => `
    <div id="qi-${idx}" class="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm flex flex-col md:flex-row items-start gap-4 hover:border-brand-blue/30 transition-all group">
      <div class="flex items-start gap-3 w-full md:w-auto">
        <input type="checkbox" onchange="toggleSel(${idx})" class="mt-1.5 w-4 h-4 cursor-pointer accent-brand-blue">
        <div class="w-44 h-28 rounded-xl overflow-hidden shrink-0 bg-slate-100 hidden md:block">
          <img src="${a.image||'https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=400&q=70'}"
               class="w-full h-full object-cover grayscale group-hover:grayscale-0 transition-all duration-500"
               onerror="this.src='https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=400&q=70'" alt="">
        </div>
      </div>
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2 mb-2">
          <span class="text-[10px] font-bold text-white ${srcBg(a.source||'')} px-2 py-0.5 rounded">${esc(a.source||'')}</span>
          <span class="text-[10px] font-semibold ${diffBadge(a.difficulty||'Easy')} px-2 py-0.5 rounded">${a.difficulty||'Easy'}</span>
          <span class="text-[10px] text-slate-400 uppercase font-bold">Just crawled</span>
        </div>
        <h3 class="text-base font-bold text-slate-900 mb-1.5 leading-tight">${esc(a.title||'')}</h3>
        <p class="text-sm text-slate-500 line-clamp-2 leading-relaxed mb-2">${esc((a.content||'').slice(0,200))}...</p>
        <div class="flex items-center gap-4 text-xs text-slate-400">
          <span><i class="fa-solid fa-clock mr-1"></i>${a.word_count||'--'} words</span>
          <span><i class="fa-solid fa-signal mr-1"></i>${a.difficulty||'Medium'}</span>
          <span><i class="fa-solid fa-clock-rotate-left mr-1"></i>${a.read_time||'5'} min</span>
          <span><i class="fa-solid fa-calendar mr-1"></i>${a.published||'--'}</span>
        </div>
      </div>
      <div class="flex md:flex-col gap-2 shrink-0 w-full md:w-auto">
        <button onclick="approveOne(${idx},this)"
          class="flex-1 md:flex-none px-5 py-2.5 bg-brand-emerald hover:bg-emerald-600 text-white rounded-xl text-xs font-bold shadow-md shadow-brand-emerald/10 transition-colors flex items-center justify-center gap-2">
          <i class="fa-solid fa-check"></i> APPROVE
        </button>
        <button onclick="rejectOne(${idx})"
          class="flex-1 md:flex-none px-5 py-2.5 bg-slate-100 hover:bg-red-50 hover:text-red-600 text-slate-500 rounded-xl text-xs font-bold transition-colors flex items-center justify-center gap-2 border border-transparent hover:border-red-100">
          <i class="fa-solid fa-xmark"></i> REJECT
        </button>
      </div>
    </div>`).join('');
}

function toggleSel(idx) { selected.has(idx)?selected.delete(idx):selected.add(idx); }
function selectAll() {
  const all=crawled.map((_,i)=>i);
  if(selected.size===all.length) selected.clear(); else all.forEach(i=>selected.add(i));
  document.querySelectorAll('#queueList input[type=checkbox]').forEach((cb,i)=>{cb.checked=selected.has(i);});
}

async function approveOne(idx, btn) {
  btn.disabled=true;
  btn.innerHTML='<i class="fa-solid fa-circle-notch fa-spin"></i> Lưu...';
  try {
    const res = await fetch('/api/approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(crawled[idx])});
    const d = await res.json();
    if(d.success) {
      btn.innerHTML='<i class="fa-solid fa-check-double"></i> Đã duyệt';
      btn.className='flex-1 md:flex-none px-5 py-2.5 bg-slate-300 text-white rounded-xl text-xs font-bold flex items-center justify-center gap-2 cursor-not-allowed';
      showToast(d.demo_mode?'⚠️ Demo mode — chưa lưu vĩnh viễn':'✅ Đã lưu vào Supabase');
      loadPublished();
    } else { btn.disabled=false; btn.innerHTML='<i class="fa-solid fa-check"></i> APPROVE'; showToast('❌ '+(d.error||'Lỗi')); }
  } catch(e) { btn.disabled=false; btn.innerHTML='<i class="fa-solid fa-check"></i> APPROVE'; showToast('❌ Lỗi kết nối'); }
}

function rejectOne(idx) {
  const el=$('qi-'+idx);
  if(el){el.style.opacity='0';el.style.transform='translateX(40px)';el.style.transition='all .3s';setTimeout(()=>el.remove(),300);}
  crawled.splice(idx,1);
  $('queueBadge').textContent=crawled.length;
  setTimeout(renderQueue,350);
}

async function batchApprove() {
  if(!selected.size){showToast('⚠️ Chưa chọn bài nào!');return;}
  let ok=0;
  for(const i of [...selected]) {
    try {
      const r=await fetch('/api/approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(crawled[i])});
      const d=await r.json(); if(d.success) ok++;
    } catch(e){}
  }
  showToast('✅ Đã duyệt '+ok+'/'+selected.size+' bài');
  selected.clear(); renderQueue(); loadPublished();
}

// Init
loadPublished();
</script>
</body></html>"""

# ═══════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════
def render_page(tmpl):
    return render_template_string(
        tmpl.replace("{{ shared_css }}", SHARED_CSS)
            .replace("{{ version }}", APP_VERSION)
    )

@app.route("/")
def student_home():
    return render_page(STUDENT_HTML)

@app.route("/admin")
def admin_home():
    return render_page(ADMIN_HTML)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
