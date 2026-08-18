# -*- coding: utf-8 -*-
"""
============================================================
  AI ENGLISH SPEED READER  v2.0
  UI/UX hoàn toàn mới theo thiết kế UXpilot:
  - Trang học sinh: sidebar navigation, WPM baseline dashboard,
    reading pane + microphone button, article cards có ảnh,
    audio speed slider, performance metrics (S/A/B/C rank)
  - Trang admin: content crawler controller, pending article queue,
    approve/reject workflow
  - Responsive: Desktop (sidebar) + Mobile (bottom nav + drawer)

  Backend : Flask + feedparser + Supabase
  Deploy  : Render + Supabase (xem README.md)
============================================================
"""

import os
import re
import html
from datetime import datetime, timezone

import feedparser
from flask import Flask, jsonify, request, render_template_string

try:
    from supabase import create_client
except ImportError:
    create_client = None

app = Flask(__name__)

# ── Supabase ─────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()
supabase = None
if SUPABASE_URL and SUPABASE_KEY and create_client:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"[WARN] Supabase: {e}")

TABLE_ARTICLES = "articles"
TABLE_SCORES   = "scores"

# ── Demo data ─────────────────────────────────────────────
DEMO_ARTICLES = [
    {
        "id": "demo-1",
        "source": "BBC",
        "title": "The Rise of Artificial Intelligence",
        "content": (
            "In recent years, artificial intelligence technology has evolved "
            "rapidly across industries. From healthcare diagnostics to autonomous "
            "vehicles, machine learning models now process billions of data points "
            "daily. Researchers at leading universities report that natural language "
            "processing systems can now summarize complex scientific papers with over "
            "ninety percent accuracy. As adoption accelerates, educators are "
            "integrating AI literacy into core curricula to prepare students for a "
            "workforce where human-machine collaboration is the new standard."
        ),
        "difficulty": "Easy",
        "image": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=600&q=70",
        "url": "",
        "read_time": "5",
    },
    {
        "id": "demo-2",
        "source": "CNN",
        "title": "The Future of Quantum Computing",
        "content": (
            "Quantum computing is breaking the silicon barrier and pushing the "
            "boundaries of what is computationally possible. Scientists at major "
            "research labs have demonstrated quantum processors capable of solving "
            "problems that would take classical computers thousands of years. "
            "Industries from pharmaceuticals to finance are watching closely, "
            "eager to harness the power of quantum algorithms for drug discovery, "
            "portfolio optimization, and cryptography. However, significant "
            "engineering challenges remain before quantum computers become "
            "commercially viable at scale."
        ),
        "difficulty": "Medium",
        "image": "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=600&q=70",
        "url": "",
        "read_time": "7",
    },
    {
        "id": "demo-3",
        "source": "Reuters",
        "title": "Urban Planning in the 21st Century",
        "content": (
            "Designing smarter megacities has become a global priority as urban "
            "populations continue to grow. City planners now rely on data analytics, "
            "sensor networks, and artificial intelligence to manage traffic flow, "
            "reduce energy consumption, and improve public services. Sustainable "
            "architecture featuring vertical gardens and solar-integrated glass "
            "facades is changing skylines from Singapore to Stockholm. The challenge "
            "ahead lies in ensuring that smart city benefits reach all residents, "
            "regardless of income or neighborhood."
        ),
        "difficulty": "Hard",
        "image": "https://images.unsplash.com/photo-1449824913935-59a10b8d2000?auto=format&fit=crop&w=600&q=70",
        "url": "",
        "read_time": "9",
    },
    {
        "id": "demo-4",
        "source": "NatGeo",
        "title": "Deep Ocean Exploration",
        "content": (
            "The deep ocean remains one of the least explored frontiers on Earth. "
            "Recent expeditions using remotely operated vehicles have discovered "
            "thousands of new species living in the crushing darkness of the abyss. "
            "Hydrothermal vents support entire ecosystems powered not by sunlight "
            "but by chemical energy. These findings challenge our assumptions about "
            "where life can thrive and have implications for the search for life "
            "on other planets and moons in our solar system."
        ),
        "difficulty": "Easy",
        "image": "https://images.unsplash.com/photo-1532094349884-543bc11b234d?auto=format&fit=crop&w=600&q=70",
        "url": "",
        "read_time": "4",
    },
]

RSS_FEEDS = {
    "BBC": "http://feeds.bbci.co.uk/news/technology/rss.xml",
    "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "CNN": "http://rss.cnn.com/rss/cnn_topstories.rss",
    "Reuters": "https://feeds.reuters.com/reuters/technologyNews",
}

DIFFICULTY_IMAGES = {
    "Easy":   "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=600&q=70",
    "Medium": "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=600&q=70",
    "Hard":   "https://images.unsplash.com/photo-1507413245164-6160d8298b31?auto=format&fit=crop&w=600&q=70",
}

def clean_html(raw):
    if not raw: return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()

def word_count(text):
    return len(text.split())

def estimate_difficulty(text):
    wc = word_count(text)
    avg_word = sum(len(w) for w in text.split()) / max(wc, 1)
    if avg_word > 6 or wc > 200: return "Hard"
    if avg_word > 4.5 or wc > 100: return "Medium"
    return "Easy"

def read_time(text):
    return max(1, round(word_count(text) / 150))

def calc_rank(wpm, accuracy):
    if accuracy >= 95 and wpm >= 130: return "S"
    if accuracy >= 90 and wpm >= 100: return "A"
    if accuracy >= 80 and wpm >= 70:  return "B"
    return "C"

# ═══════════════════════════════════════════════════════════
# BACKEND APIs
# ═══════════════════════════════════════════════════════════

@app.route("/api/crawl", methods=["POST"])
def api_crawl():
    found = []
    for source, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:5]:
                title   = clean_html(entry.get("title", ""))
                summary = clean_html(entry.get("summary", entry.get("description", "")))
                link    = entry.get("link", "")
                if len(summary.split()) < 25: continue
                diff = estimate_difficulty(summary)
                found.append({
                    "source":     source,
                    "title":      title,
                    "content":    summary,
                    "url":        link,
                    "difficulty": diff,
                    "image":      DIFFICULTY_IMAGES.get(diff, DIFFICULTY_IMAGES["Medium"]),
                    "read_time":  str(read_time(summary)),
                    "word_count": word_count(summary),
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
        "source":     data.get("source", ""),
        "url":        data.get("url", ""),
        "content":    data["content"],
        "difficulty": data.get("difficulty", "Medium"),
        "image":      data.get("image", DIFFICULTY_IMAGES["Medium"]),
        "read_time":  data.get("read_time", "5"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if supabase is None:
        return jsonify({"success": True, "demo_mode": True, "data": record})
    try:
        res = supabase.table(TABLE_ARTICLES).insert(record).execute()
        return jsonify({"success": True, "data": res.data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/articles", methods=["GET"])
def api_articles():
    if supabase is None:
        return jsonify({"success": True, "demo_mode": True, "articles": DEMO_ARTICLES})
    try:
        res = (supabase.table(TABLE_ARTICLES)
               .select("*").order("created_at", desc=True).limit(20).execute())
        articles = res.data or []
        if not articles:
            return jsonify({"success": True, "demo_mode": True, "articles": DEMO_ARTICLES})
        return jsonify({"success": True, "articles": articles})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "articles": DEMO_ARTICLES})

@app.route("/api/save_score", methods=["POST"])
def api_save_score():
    data = request.get_json(force=True, silent=True) or {}
    if not data.get("student_name"):
        return jsonify({"success": False, "error": "Thiếu tên học sinh"}), 400
    record = {
        "student_name":  data["student_name"],
        "article_title": data.get("article_title", ""),
        "wpm":           data.get("wpm", 0),
        "accuracy":      data.get("accuracy", 0),
        "rank":          data.get("rank", "C"),
        "created_at":    datetime.now(timezone.utc).isoformat(),
    }
    if supabase is None:
        return jsonify({"success": True, "demo_mode": True, "data": record})
    try:
        res = supabase.table(TABLE_SCORES).insert(record).execute()
        return jsonify({"success": True, "data": res.data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ═══════════════════════════════════════════════════════════
# SHARED CSS
# ═══════════════════════════════════════════════════════════
SHARED_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Merriweather:wght@400;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/js/all.min.js" crossorigin="anonymous"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {
  theme: { extend: {
    fontFamily: { sans: ['"Plus Jakarta Sans"', 'sans-serif'], serif: ['Merriweather','serif'] },
    colors: { brand: { dark:'#1a252f', blue:'#2563eb', emerald:'#2ecc71', graybg:'#f8fafc' } }
  }}
}
</script>
<style>
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#cbd5e1;border-radius:10px}
.no-scrollbar::-webkit-scrollbar{display:none}
.no-scrollbar{-ms-overflow-style:none;scrollbar-width:none}
@keyframes pulse-ring{0%{transform:scale(.85);opacity:.6}100%{transform:scale(1.4);opacity:0}}
.pulse-ring::before{content:"";position:absolute;inset:-6px;border-radius:9999px;border:2px solid #2563eb;animation:pulse-ring 2s cubic-bezier(.4,0,.6,1) infinite}
@keyframes wave{0%{height:14%}100%{height:100%}}
.wave-bar{animation:wave 1.2s ease-in-out infinite alternate}
.sidebar-drawer{transform:translateX(-100%);transition:transform .3s ease-in-out}
.sidebar-drawer.open{transform:translateX(0)}
.overlay{opacity:0;pointer-events:none;transition:opacity .3s ease-in-out}
.overlay.show{opacity:1;pointer-events:auto}
.active-word::after{content:"";position:absolute;bottom:2px;left:0;right:0;height:38%;background:rgba(46,204,113,.25);z-index:-1;border-radius:3px}
.word-span{transition:all .3s ease;border-radius:4px;padding:1px 2px}
.word-span.read{background:#dcfce7;color:#15803d;font-weight:700}
.word-span.current{background:#fef9c3}
</style>
"""

# ═══════════════════════════════════════════════════════════
# STUDENT PAGE  ( / )
# ═══════════════════════════════════════════════════════════
STUDENT_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>AI Speed Reader — Learning Room</title>
{{ shared_css }}
</head>
<body class="bg-brand-graybg text-slate-800 font-sans antialiased h-screen overflow-hidden flex">

<!-- ── MOBILE OVERLAY ── -->
<div id="overlay" class="overlay fixed inset-0 bg-slate-900/60 z-40" onclick="closeSidebar()"></div>

<!-- ══════════ SIDEBAR ══════════ -->
<aside id="sidebar"
  class="sidebar-drawer fixed lg:static top-0 left-0 bottom-0 w-[280px] bg-white border-r border-slate-200
         flex flex-col shrink-0 z-50 shadow-xl lg:shadow-sm lg:translate-x-0">

  <!-- Logo -->
  <div class="h-20 flex items-center px-8 border-b border-slate-100">
    <div class="flex items-center gap-3">
      <div class="relative w-9 h-9 flex items-center justify-center">
        <svg width="36" height="36" viewBox="0 0 36 36" fill="none" class="absolute inset-0 opacity-30">
          <circle cx="18" cy="18" r="16" stroke="#2ecc71" stroke-width="4"/>
        </svg>
        <div class="flex items-center gap-[3px] h-5 absolute z-10">
          <span class="w-[2px] bg-brand-emerald rounded-full" style="height:40%"></span>
          <span class="w-[2px] bg-brand-emerald rounded-full" style="height:100%"></span>
          <span class="w-[2px] bg-brand-emerald rounded-full" style="height:60%"></span>
          <span class="w-[2px] bg-brand-emerald rounded-full" style="height:90%"></span>
        </div>
      </div>
      <span class="text-xl font-bold text-slate-900 tracking-tight">SpeedAI</span>
    </div>
  </div>

  <!-- Profile -->
  <div class="px-8 py-6 border-b border-slate-100">
    <div class="relative w-16 h-16 mx-auto mb-3 rounded-full overflow-hidden border-2 border-white shadow-md">
      <img src="https://storage.googleapis.com/uxpilot-auth.appspot.com/avatars/avatar-2.jpg" class="w-full h-full object-cover" alt="">
    </div>
    <h3 class="text-center font-semibold text-slate-900 text-sm" id="sidebarName">Student: Alex</h3>
    <div class="flex justify-center mt-2">
      <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-50 text-brand-blue text-xs font-semibold border border-blue-100">
        <i class="fa-solid fa-gem text-[10px]"></i> Pro Reader
      </span>
    </div>
  </div>

  <!-- Nav -->
  <nav class="flex-1 px-5 py-6 space-y-1.5 overflow-y-auto">
    <a href="#" onclick="showSection('learning');closeSidebar()" 
       class="nav-link active flex items-center gap-3 px-4 py-3 bg-brand-dark text-white rounded-xl shadow-sm relative">
      <div class="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 bg-brand-emerald rounded-r-md"></div>
      <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-white/10 text-brand-emerald">
        <i class="fa-solid fa-book-open-reader text-sm"></i>
      </div>
      <span class="font-medium text-sm ml-1">Learning Room</span>
    </a>
    <a href="#" onclick="showSection('library');closeSidebar()"
       class="nav-link flex items-center gap-3 px-4 py-3 text-slate-500 hover:bg-slate-50 hover:text-slate-900 rounded-xl transition-colors">
      <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-100 text-slate-500">
        <i class="fa-solid fa-newspaper text-sm"></i>
      </div>
      <span class="font-medium text-sm">Article Library</span>
    </a>
    <a href="#" onclick="showSection('metrics');closeSidebar()"
       class="nav-link flex items-center gap-3 px-4 py-3 text-slate-500 hover:bg-slate-50 hover:text-slate-900 rounded-xl transition-colors">
      <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-100 text-slate-500">
        <i class="fa-solid fa-chart-line text-sm"></i>
      </div>
      <span class="font-medium text-sm">Performance Metrics</span>
    </a>
    <a href="/admin"
       class="flex items-center gap-3 px-4 py-3 text-slate-500 hover:bg-slate-50 hover:text-slate-900 rounded-xl transition-colors">
      <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-100 text-slate-500">
        <i class="fa-solid fa-sliders text-sm"></i>
      </div>
      <span class="font-medium text-sm">Admin Panel</span>
    </a>
  </nav>

  <!-- Daily Streak -->
  <div class="p-5 border-t border-slate-100">
    <div class="rounded-2xl bg-slate-50 p-4 border border-slate-100">
      <div class="flex items-center gap-2 text-sm font-semibold text-slate-800 mb-3">
        <i class="fa-solid fa-fire text-orange-400"></i> Daily Streak: <span id="streakCount">0</span>
      </div>
      <div class="flex justify-between items-center mb-2">
        <span class="text-xs text-slate-500">Weekly goal</span>
        <span class="text-xs font-bold text-brand-blue" id="goalPct">0%</span>
      </div>
      <div class="w-full bg-slate-200 rounded-full h-1.5">
        <div class="bg-brand-blue h-1.5 rounded-full transition-all" id="goalBar" style="width:0%"></div>
      </div>
    </div>
  </div>
</aside>

<!-- ══════════ MAIN ══════════ -->
<main class="flex-1 flex flex-col min-w-0 overflow-hidden">

  <!-- Top toolbar -->
  <header class="h-20 px-4 lg:px-8 flex items-center justify-between border-b border-slate-200 bg-white shrink-0">
    <div class="flex items-center gap-3">
      <!-- Hamburger (mobile) -->
      <button onclick="openSidebar()" class="lg:hidden w-10 h-10 flex items-center justify-center rounded-xl bg-slate-50 border border-slate-200 text-slate-600">
        <i class="fa-solid fa-bars-staggered"></i>
      </button>
      <div class="relative flex-1 max-w-[400px] hidden md:block">
        <i class="fa-solid fa-magnifying-glass absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 text-sm"></i>
        <input id="searchInput" type="text" placeholder="Search articles, topics..."
               class="w-full pl-11 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue/20 placeholder:text-slate-400">
      </div>
    </div>
    <div class="flex items-center gap-2 lg:gap-3">
      <!-- Student name input -->
      <div class="relative">
        <i class="fa-solid fa-user absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-xs"></i>
        <input id="studentName" type="text" placeholder="Tên học sinh..." maxlength="40"
               class="pl-8 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm w-32 lg:w-44 focus:outline-none focus:ring-2 focus:ring-brand-blue/20"
               oninput="updateStudentUI()">
      </div>
      <button onclick="window.location='/admin'" class="flex items-center gap-2 px-3 py-2.5 bg-white border border-slate-200 rounded-xl text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors hidden lg:flex">
        <i class="fa-solid fa-gear text-slate-400"></i> Admin
      </button>
    </div>
  </header>

  <!-- Scrollable content -->
  <div class="flex-1 overflow-y-auto p-4 lg:p-8" id="mainScroll">
    <div class="max-w-[1400px] mx-auto space-y-6">

      <!-- ── SECTION: LEARNING ROOM ── -->
      <div id="section-learning">

        <!-- HERO BANNER (12-col grid) -->
        <section class="grid grid-cols-12 gap-5 mb-6">
          <!-- WPM Baseline -->
          <div class="col-span-12 lg:col-span-7 bg-brand-dark rounded-3xl p-7 relative overflow-hidden flex flex-col justify-between min-h-[200px]">
            <div class="absolute top-0 right-0 w-64 h-64 bg-brand-blue/20 blur-[60px] rounded-full pointer-events-none"></div>
            <div class="relative z-10">
              <div class="flex items-center gap-2 text-brand-emerald text-xs font-bold tracking-widest uppercase mb-3">
                <i class="fa-solid fa-bolt"></i> Your Baseline
              </div>
              <div class="flex items-baseline gap-3">
                <h1 class="text-5xl lg:text-6xl font-extrabold text-white leading-none" id="heroWpm">--</h1>
                <span class="text-2xl font-semibold text-slate-400">WPM</span>
              </div>
              <p class="text-slate-400 text-sm mt-3 max-w-sm" id="heroSubtitle">
                Nhập tên và bắt đầu luyện đọc để xem kết quả của bạn.
              </p>
            </div>
            <button onclick="document.getElementById('studentName').focus()"
                    class="relative z-10 self-start mt-5 px-5 py-2.5 bg-brand-blue hover:bg-blue-600 text-white rounded-xl text-sm font-semibold transition-colors">
              Configure Calibration <i class="fa-solid fa-chevron-right text-xs ml-1"></i>
            </button>
          </div>

          <!-- Word Retention Bar Chart -->
          <div class="col-span-12 lg:col-span-5 bg-white rounded-3xl p-6 border border-slate-100 shadow-sm flex flex-col">
            <div class="flex items-center justify-between mb-1">
              <h3 class="font-semibold text-slate-900">Word Retention Rate</h3>
              <span class="text-xs font-semibold text-brand-emerald bg-emerald-50 px-2 py-0.5 rounded-md" id="retentionDelta">+0%</span>
            </div>
            <p class="text-xs text-slate-400 mb-3">Last 7 sessions</p>
            <div class="flex-1 flex items-end gap-2 pt-2" id="retentionBars">
              <!-- bars rendered by JS -->
            </div>
          </div>
        </section>

        <!-- READING AREA + RIGHT PANEL -->
        <section class="grid grid-cols-12 gap-5 mb-6">

          <!-- Reading Pane (8 cols) -->
          <div class="col-span-12 lg:col-span-8 bg-white rounded-3xl p-6 border border-slate-100 shadow-sm flex flex-col">
            <!-- Article header -->
            <div class="flex items-start justify-between mb-5">
              <div id="articleHeader">
                <div class="flex items-center gap-2 mb-1">
                  <span class="text-[10px] font-bold text-white bg-red-500 px-2 py-0.5 rounded" id="articleSource">--</span>
                  <span class="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded" id="articleDifficulty">Easy</span>
                </div>
                <h3 class="text-base lg:text-lg font-bold text-slate-900" id="articleTitle">Chọn một bài báo bên dưới để bắt đầu</h3>
              </div>
              <div class="flex items-center gap-3 text-slate-400 shrink-0 ml-2">
                <button class="hover:text-slate-700 transition-colors" title="Font size" onclick="cycleFontSize()"><i class="fa-solid fa-font text-lg"></i></button>
                <button class="hover:text-slate-700 transition-colors" title="Focus mode" onclick="toggleFocus()"><i class="fa-solid fa-glasses text-lg"></i></button>
              </div>
            </div>

            <!-- Text area -->
            <div id="readingPane" class="overflow-y-auto pr-1 no-scrollbar flex-1" style="height:320px;">
              <p class="font-serif text-[20px] lg:text-[22px] leading-[2.1] text-slate-700" id="readingText">
                <span class="text-slate-400 text-base">Hãy chọn một bài báo từ danh sách bên dưới, sau đó nhấn nút microphone màu xanh để bắt đầu luyện đọc. Văn bản sẽ hiển thị tại đây và từ nào bạn đọc đúng sẽ tự động chuyển sang màu xanh lá.</span>
              </p>
            </div>

            <!-- Controls -->
            <div class="mt-5 flex items-center justify-center gap-6 pt-2 border-t border-slate-50">
              <button id="btnPrev" onclick="prevArticle()"
                      class="w-12 h-12 rounded-full bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-700 flex items-center justify-center transition-colors">
                <i class="fa-solid fa-backward-step text-sm"></i>
              </button>
              <!-- MIC BUTTON -->
              <button id="btnMic" onclick="toggleReading()"
                      class="relative w-20 h-20 rounded-full bg-brand-blue text-white flex items-center justify-center shadow-lg shadow-blue-500/30 pulse-ring hover:bg-blue-600 transition-colors">
                <i class="fa-solid fa-microphone text-3xl" id="micIcon"></i>
              </button>
              <button id="btnNext" onclick="nextArticle()"
                      class="w-12 h-12 rounded-full bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-700 flex items-center justify-center transition-colors">
                <i class="fa-solid fa-forward-step text-sm"></i>
              </button>
              <div class="pl-2">
                <p class="text-sm font-bold text-slate-900" id="micLabel">START READING</p>
                <p class="text-xs text-slate-400" id="micSub">Voice tracking active</p>
              </div>
            </div>
          </div>

          <!-- Right column (4 cols) -->
          <div class="col-span-12 lg:col-span-4 space-y-5">

            <!-- Audio Speed Slider -->
            <div class="bg-white rounded-3xl p-6 border border-slate-100 shadow-sm">
              <div class="flex items-center justify-between mb-5">
                <h3 class="font-semibold text-slate-900 text-sm">Audio Speed</h3>
                <span class="text-xs font-bold text-brand-blue bg-blue-50 px-2 py-0.5 rounded-md" id="speedLabel">420 WPM</span>
              </div>
              <!-- Track -->
              <div class="relative h-10 mb-2">
                <div class="absolute top-1/2 -translate-y-1/2 left-0 right-0 h-1.5 bg-slate-100 rounded-full"></div>
                <div class="absolute top-1/2 -translate-y-1/2 left-0 h-1.5 bg-brand-emerald rounded-full transition-all" id="speedFill" style="width:52%"></div>
                <input type="range" min="100" max="800" value="420" step="10" id="speedSlider"
                       oninput="updateSpeed(this.value)"
                       class="absolute inset-0 w-full opacity-0 cursor-pointer h-full">
                <div class="absolute top-1/2 -translate-y-1/2 w-5 h-5 bg-white border-2 border-brand-emerald rounded-full shadow-sm pointer-events-none flex items-center justify-center transition-all" id="speedThumb" style="left:calc(52% - 10px)">
                  <div class="w-2 h-2 bg-brand-emerald rounded-full"></div>
                </div>
              </div>
              <div class="flex justify-between text-[10px] text-slate-400 font-medium mb-5">
                <span>100</span><span>300</span><span>500</span><span>700</span><span>800</span>
              </div>
              <!-- Waveform visualizer -->
              <div class="flex items-center justify-center gap-[3px] h-10 px-2" id="waveform">
                <!-- bars rendered by JS -->
              </div>
            </div>

            <!-- Metrics (3 cards) -->
            <div class="grid grid-cols-3 gap-3">
              <div class="bg-white rounded-3xl p-4 border border-slate-100 shadow-sm flex flex-col">
                <div class="w-8 h-8 rounded-xl bg-slate-50 border border-slate-100 flex items-center justify-center text-slate-500 mb-2">
                  <i class="fa-solid fa-gauge-high text-xs"></i>
                </div>
                <p class="text-[10px] text-slate-400 mb-1">Speed</p>
                <p class="text-base font-bold text-slate-900"><span id="metricWpm">--</span> <span class="text-[10px] font-medium text-slate-400">WPM</span></p>
                <div class="mt-auto pt-2 flex items-center gap-1 text-brand-emerald text-[10px] font-bold">
                  <i class="fa-solid fa-arrow-trend-up"></i> <span id="metricWpmDelta">--</span>
                </div>
              </div>
              <div class="bg-white rounded-3xl p-4 border border-slate-100 shadow-sm flex flex-col">
                <div class="w-8 h-8 rounded-xl bg-slate-50 border border-slate-100 flex items-center justify-center text-slate-500 mb-2">
                  <i class="fa-solid fa-bullseye text-xs"></i>
                </div>
                <p class="text-[10px] text-slate-400 mb-1">Accuracy</p>
                <p class="text-base font-bold text-slate-900"><span id="metricAcc">--</span><span class="text-[10px] font-medium text-slate-400">%</span></p>
                <div class="mt-auto pt-2 flex items-center gap-1 text-brand-emerald text-[10px] font-bold">
                  <i class="fa-solid fa-arrow-trend-up"></i> <span id="metricAccDelta">--</span>
                </div>
              </div>
              <div class="bg-white rounded-3xl p-4 border border-slate-100 shadow-sm flex flex-col items-center justify-center">
                <div class="w-14 h-14 rounded-full bg-emerald-50 flex items-center justify-center mb-1">
                  <span class="text-3xl font-extrabold text-brand-emerald" id="metricRank">--</span>
                </div>
                <p class="text-[10px] text-slate-400 font-medium">Grade Rank</p>
              </div>
            </div>
          </div>
        </section>

        <!-- RECOMMENDED ARTICLES -->
        <section class="mb-6">
          <div class="flex items-center justify-between mb-5">
            <h2 class="text-xl font-bold text-slate-900">Recommended Articles</h2>
            <a href="#" onclick="showSection('library');return false" class="text-sm font-semibold text-brand-blue hover:underline">
              View library <i class="fa-solid fa-chevron-right text-xs ml-1"></i>
            </a>
          </div>
          <div id="articleGrid" class="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="col-span-2 lg:col-span-4 text-center text-slate-400 py-10">
              <i class="fa-solid fa-spinner fa-spin text-2xl mb-2"></i>
              <p class="text-sm">Đang tải bài báo...</p>
            </div>
          </div>
        </section>
      </div><!-- /section-learning -->

      <!-- ── SECTION: LIBRARY ── -->
      <div id="section-library" class="hidden">
        <div class="flex items-center justify-between mb-6">
          <h2 class="text-2xl font-bold text-slate-900">Article Library</h2>
          <span class="text-sm text-slate-400" id="libraryCount">-- bài báo</span>
        </div>
        <div id="libraryGrid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        </div>
      </div>

      <!-- ── SECTION: METRICS ── -->
      <div id="section-metrics" class="hidden">
        <h2 class="text-2xl font-bold text-slate-900 mb-6">Performance Metrics</h2>
        <div id="metricsHistory" class="space-y-4">
          <div class="bg-white rounded-2xl p-8 border border-slate-100 shadow-sm text-center text-slate-400">
            <i class="fa-solid fa-chart-line text-4xl mb-3 text-slate-200"></i>
            <p class="font-medium">Chưa có dữ liệu luyện tập.</p>
            <p class="text-sm mt-1">Hãy hoàn thành ít nhất 1 bài đọc để xem thống kê.</p>
          </div>
        </div>
      </div>

    </div><!-- /max-w -->
  </div><!-- /scroll -->

  <!-- MOBILE BOTTOM NAV -->
  <nav class="lg:hidden fixed bottom-0 left-0 right-0 h-16 bg-white border-t border-slate-100 flex items-center justify-around px-4 z-30 shadow-[0_-4px_10px_rgba(0,0,0,0.03)]">
    <button onclick="showSection('learning')" class="bottom-nav-btn flex flex-col items-center gap-1 text-brand-blue">
      <i class="fa-solid fa-house-chimney text-lg"></i>
      <span class="text-[9px] font-bold uppercase">Home</span>
    </button>
    <button onclick="showSection('library')" class="bottom-nav-btn flex flex-col items-center gap-1 text-slate-400">
      <i class="fa-solid fa-book-open text-lg"></i>
      <span class="text-[9px] font-bold uppercase">Library</span>
    </button>
    <button onclick="showSection('metrics')" class="bottom-nav-btn flex flex-col items-center gap-1 text-slate-400">
      <i class="fa-solid fa-chart-simple text-lg"></i>
      <span class="text-[9px] font-bold uppercase">Stats</span>
    </button>
    <button onclick="window.location='/admin'" class="flex flex-col items-center gap-1 text-slate-400">
      <i class="fa-solid fa-gear text-lg"></i>
      <span class="text-[9px] font-bold uppercase">Admin</span>
    </button>
  </nav>

</main><!-- /main -->

<!-- ══════════ TOAST ══════════ -->
<div id="toast" class="fixed bottom-20 lg:bottom-6 left-1/2 -translate-x-1/2 bg-brand-dark text-white px-5 py-3 rounded-xl text-sm shadow-xl opacity-0 pointer-events-none transition-all z-[100]"></div>

<script>
// ════════════════════════════════════════════
// STATE
// ════════════════════════════════════════════
let articles      = [];
let selIdx        = -1;
let words         = [];
let matchIdx      = 0;
let spokenCount   = 0;
let correctCount  = 0;
let startTime     = null;
let recognition   = null;
let isListening   = false;
let fontSize      = 22;
let sessionHistory = JSON.parse(localStorage.getItem('speedai_history') || '[]');
let streakDays    = parseInt(localStorage.getItem('speedai_streak') || '0');

const $ = id => document.getElementById(id);

// ── Sidebar ──
function openSidebar()  { $('sidebar').classList.add('open'); $('overlay').classList.add('show'); }
function closeSidebar() { $('sidebar').classList.remove('open'); $('overlay').classList.remove('show'); }

// ── Section nav ──
function showSection(name) {
  ['learning','library','metrics'].forEach(s => {
    const el = $('section-' + s);
    if (el) el.classList.toggle('hidden', s !== name);
  });
  if (name === 'library') renderLibrary();
  if (name === 'metrics') renderMetrics();
  // Update bottom nav color
  document.querySelectorAll('.bottom-nav-btn').forEach((b, i) => {
    b.className = b.className.replace(/text-brand-blue|text-slate-400/g, '');
    const active = ['learning','library','metrics'][i] === name;
    b.classList.add(active ? 'text-brand-blue' : 'text-slate-400');
  });
}

// ── Student UI ──
function updateStudentUI() {
  const name = $('studentName').value.trim() || 'Alex';
  $('sidebarName').textContent = 'Student: ' + name;
}

// ── Toast ──
function showToast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.style.opacity = '1';
  setTimeout(() => { t.style.opacity = '0'; }, 2800);
}

// ── Waveform render ──
function renderWaveform(active = false) {
  const heights = [30,60,40,80,100,70,50,35,55,25];
  $('waveform').innerHTML = heights.map((h, i) => `
    <span class="w-1 rounded-full wave-bar ${active && i>2 && i<7 ? 'bg-brand-emerald' : 'bg-slate-200'}"
          style="height:${h}%;animation-delay:${i*0.1}s"></span>
  `).join('');
}

// ── Speed slider ──
function updateSpeed(val) {
  const pct = ((val - 100) / 700) * 100;
  $('speedLabel').textContent = val + ' WPM';
  $('speedFill').style.width = pct + '%';
  $('speedThumb').style.left = 'calc(' + pct + '% - 10px)';
}

// ── Font size cycle ──
function cycleFontSize() {
  const sizes = [18, 20, 22, 24, 26];
  const idx = sizes.indexOf(fontSize);
  fontSize = sizes[(idx + 1) % sizes.length];
  $('readingText').style.fontSize = fontSize + 'px';
}

// ── Focus mode ──
let focusMode = false;
function toggleFocus() {
  focusMode = !focusMode;
  const pane = $('readingPane');
  pane.style.height = focusMode ? '520px' : '320px';
}

// ── Retention bar chart ──
function renderRetentionBars(history) {
  const days = ['M','T','W','T','F','S','S'];
  const vals = [40,55,48,88,64,72,96];
  const colors = [false,false,false,true,false,false,true];
  $('retentionBars').innerHTML = days.map((d,i) => `
    <div class="flex-1 flex flex-col items-center gap-1">
      <div class="w-full ${colors[i] ? 'bg-brand-blue' : 'bg-slate-100'} rounded-t-md transition-all"
           style="height:${vals[i]}%"></div>
      <span class="text-[10px] text-slate-400">${d}</span>
    </div>
  `).join('');

  if (history.length > 0) {
    const delta = history.length >= 2
      ? Math.round(history[history.length-1].accuracy - history[history.length-2].accuracy)
      : 0;
    $('retentionDelta').textContent = (delta >= 0 ? '+' : '') + delta + '%';
  }
}

// ── Article cards ──
function diffColor(diff) {
  return { Easy:'emerald', Medium:'yellow', Hard:'amber' }[diff] || 'emerald';
}
function sourceBg(src) {
  const m = { BBC:'bg-red-500', CNN:'bg-red-600', Reuters:'bg-slate-800', NatGeo:'bg-blue-600' };
  return m[src] || 'bg-slate-700';
}

function renderArticleCard(a, idx) {
  const dc = diffColor(a.difficulty || 'Easy');
  const sb = sourceBg(a.source || '');
  return `
    <article onclick="selectArticle(${idx})"
             class="article-card bg-white rounded-3xl border border-slate-100 shadow-sm overflow-hidden cursor-pointer hover:shadow-md hover:-translate-y-1 transition-all group ${selIdx===idx?'ring-2 ring-brand-blue':''}" data-idx="${idx}">
      <div class="relative h-36 overflow-hidden">
        <img src="${a.image || 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&q=70'}"
             alt="${a.title}"
             class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
             onerror="this.src='https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&q=70'">
        <span class="absolute top-3 left-3 text-[10px] font-bold text-white ${sb} px-2 py-0.5 rounded">${a.source||'--'}</span>
      </div>
      <div class="p-4">
        <div class="flex items-center gap-2 mb-2">
          <span class="text-[10px] font-semibold text-${dc}-700 bg-${dc}-50 px-2 py-0.5 rounded">${a.difficulty||'Easy'}</span>
          <span class="text-[10px] text-slate-400">${a.read_time||'5'} min</span>
        </div>
        <h4 class="text-sm font-bold text-slate-900 leading-snug mb-1 line-clamp-2">${a.title||''}</h4>
        <p class="text-xs text-slate-400 line-clamp-1">${(a.content||'').slice(0,80)}...</p>
      </div>
    </article>`;
}

function renderArticleGrid() {
  if (!articles.length) {
    $('articleGrid').innerHTML = '<div class="col-span-4 text-center text-slate-400 py-10"><i class="fa-solid fa-newspaper text-2xl mb-2"></i><p class="text-sm">Chưa có bài báo. Admin hãy quét và duyệt bài.</p></div>';
    return;
  }
  $('articleGrid').innerHTML = articles.slice(0,4).map((a,i) => renderArticleCard(a,i)).join('');
}

function renderLibrary() {
  if (!articles.length) {
    $('libraryGrid').innerHTML = '<div class="text-center text-slate-400 py-10 col-span-3"><p>Chưa có bài báo</p></div>';
    return;
  }
  $('libraryCount').textContent = articles.length + ' bài báo';
  $('libraryGrid').innerHTML = articles.map((a,i) => renderArticleCard(a,i)).join('');
}

function selectArticle(idx) {
  selIdx = idx;
  const a = articles[idx];
  // Update reading pane header
  $('articleSource').textContent = a.source || '--';
  $('articleDifficulty').textContent = a.difficulty || 'Easy';
  $('articleTitle').textContent = a.title || '';
  // Render words
  buildReadingText(a.content || '');
  // Scroll to reading area on mobile
  $('section-library').classList.add('hidden');
  $('section-metrics').classList.add('hidden');
  $('section-learning').classList.remove('hidden');
  setTimeout(() => {
    document.querySelector('section.grid.grid-cols-12.gap-5.mb-6 + section').scrollIntoView({behavior:'smooth',block:'start'});
  }, 100);
  renderArticleGrid();
  showToast('📖 Đã chọn: ' + (a.title||'').slice(0,40) + '...');
}

function prevArticle() {
  if (!articles.length) return;
  selectArticle((selIdx <= 0 ? articles.length : selIdx) - 1);
}
function nextArticle() {
  if (!articles.length) return;
  selectArticle((selIdx + 1) % articles.length);
}

// ── Reading text ──
function normalizeWord(w) { return (w||'').toLowerCase().replace(/[^a-z0-9']/g,''); }

function buildReadingText(content) {
  const rawWords = content.trim().split(/\s+/);
  words = rawWords.map(w => ({ display: w, clean: normalizeWord(w) })).filter(w => w.clean);
  matchIdx = 0; spokenCount = 0; correctCount = 0;
  $('readingText').innerHTML = words.map((w,i) =>
    `<span class="word-span" id="ws-${i}">${w.display} </span>`
  ).join('');
  if (words.length) $('ws-0').classList.add('current');
}

function markWord(i) {
  const el = $('ws-' + i);
  if (!el) return;
  el.classList.remove('current');
  el.classList.add('read');
  el.scrollIntoView({ behavior:'smooth', block:'center' });
  const next = $('ws-' + (i+1));
  if (next) next.classList.add('current');
}

// ── Speech recognition ──
function toggleReading() {
  if (!articles.length || selIdx < 0) {
    showToast('⚠️ Hãy chọn một bài báo trước!');
    return;
  }
  const name = $('studentName').value.trim();
  if (!name) { showToast('⚠️ Hãy nhập tên học sinh!'); return; }
  if (isListening) stopReading(); else startReading();
}

function startReading() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { showToast('❌ Trình duyệt không hỗ trợ Speech API. Hãy dùng Chrome.'); return; }
  recognition = new SR();
  recognition.lang = 'en-US';
  recognition.continuous = true;
  recognition.interimResults = true;

  recognition.onresult = e => {
    let transcript = '';
    for (let i = e.resultIndex; i < e.results.length; i++)
      transcript += ' ' + e.results[i][0].transcript;
    transcript.trim().split(/\s+/).map(normalizeWord).filter(Boolean).forEach(sw => {
      if (matchIdx >= words.length) return;
      spokenCount++;
      if (sw === words[matchIdx].clean) { correctCount++; markWord(matchIdx); matchIdx++; }
    });
    if (matchIdx >= words.length) finishReading();
  };
  recognition.onerror = () => {};
  recognition.onend = () => { isListening = false; updateMicUI(false); };
  recognition.start();
  isListening = true;
  startTime = performance.now();
  updateMicUI(true);
  renderWaveform(true);
}

function stopReading() {
  if (recognition && isListening) { recognition.stop(); }
  finishReading();
}

function finishReading() {
  if (recognition) { try { recognition.stop(); } catch(e){} }
  isListening = false;
  updateMicUI(false);
  renderWaveform(false);
  if (!startTime) return;

  const elapsed = Math.max((performance.now() - startTime) / 60000, 0.05);
  const wpm = Math.round(matchIdx / elapsed);
  const accuracy = spokenCount > 0 ? Math.round((correctCount / spokenCount) * 100) : 0;
  const rank = calcRank(wpm, accuracy);

  // Update metrics panel
  $('metricWpm').textContent = wpm;
  $('metricAcc').textContent = accuracy;
  $('metricRank').textContent = rank;
  $('metricRank').className = 'text-3xl font-extrabold ' + rankColor(rank);
  $('metricWpmDelta').textContent = '+' + wpm;
  $('metricAccDelta').textContent = '+' + accuracy + '%';

  // Update hero
  $('heroWpm').textContent = wpm;
  $('heroSubtitle').textContent = `Độ chính xác ${accuracy}% • Xếp hạng ${rank} • Đọc xong ${matchIdx} từ`;

  // Save history
  const record = { wpm, accuracy, rank, title: articles[selIdx]?.title || '', date: new Date().toISOString() };
  sessionHistory.push(record);
  localStorage.setItem('speedai_history', JSON.stringify(sessionHistory.slice(-50)));

  // Streak
  streakDays++;
  localStorage.setItem('speedai_streak', streakDays);
  $('streakCount').textContent = streakDays;
  const goalPct = Math.min(100, Math.round((streakDays % 7) / 7 * 100));
  $('goalPct').textContent = goalPct + '%';
  $('goalBar').style.width = goalPct + '%';

  renderRetentionBars(sessionHistory);
  showToast(`✅ Kết quả: ${wpm} WPM | ${accuracy}% | Rank ${rank}`);

  // Save to API
  saveScore(wpm, accuracy, rank);
  startTime = null;
}

function updateMicUI(active) {
  const btn = $('btnMic');
  if (active) {
    btn.classList.replace('bg-brand-blue','bg-red-500');
    btn.classList.replace('shadow-blue-500/30','shadow-red-500/30');
    $('micIcon').className = 'fa-solid fa-stop text-3xl';
    $('micLabel').textContent = 'STOP READING';
    $('micSub').textContent = 'Đang nghe... đọc to bài báo';
  } else {
    btn.classList.replace('bg-red-500','bg-brand-blue');
    btn.classList.replace('shadow-red-500/30','shadow-blue-500/30');
    $('micIcon').className = 'fa-solid fa-microphone text-3xl';
    $('micLabel').textContent = 'START READING';
    $('micSub').textContent = 'Voice tracking active';
  }
}

function calcRank(wpm, acc) {
  if (acc >= 95 && wpm >= 130) return 'S';
  if (acc >= 90 && wpm >= 100) return 'A';
  if (acc >= 80 && wpm >= 70)  return 'B';
  return 'C';
}
function rankColor(rank) {
  return { S:'text-brand-emerald', A:'text-blue-500', B:'text-yellow-500', C:'text-red-400' }[rank] || 'text-brand-emerald';
}

async function saveScore(wpm, accuracy, rank) {
  try {
    await fetch('/api/save_score', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        student_name: $('studentName').value.trim() || 'Anonymous',
        article_title: articles[selIdx]?.title || '',
        wpm, accuracy, rank
      })
    });
  } catch(e) {}
}

// ── Metrics history ──
function renderMetrics() {
  if (!sessionHistory.length) return;
  $('metricsHistory').innerHTML = sessionHistory.slice().reverse().slice(0,10).map((h,i) => `
    <div class="bg-white rounded-2xl p-5 border border-slate-100 shadow-sm flex items-center gap-5">
      <div class="w-14 h-14 rounded-full bg-emerald-50 flex items-center justify-center shrink-0">
        <span class="text-2xl font-extrabold ${rankColor(h.rank)}">${h.rank}</span>
      </div>
      <div class="flex-1 min-w-0">
        <p class="font-semibold text-slate-900 text-sm truncate">${h.title || 'Bài luyện tập'}</p>
        <p class="text-xs text-slate-400 mt-0.5">${new Date(h.date).toLocaleString('vi-VN')}</p>
      </div>
      <div class="text-right shrink-0">
        <p class="text-lg font-extrabold text-slate-900">${h.wpm} <span class="text-xs text-slate-400 font-normal">WPM</span></p>
        <p class="text-xs text-brand-emerald font-bold">${h.accuracy}% accuracy</p>
      </div>
    </div>
  `).join('');
}

// ── Load articles ──
async function loadArticles() {
  try {
    const res = await fetch('/api/articles');
    const data = await res.json();
    articles = data.articles || [];
  } catch(e) { articles = []; }
  renderArticleGrid();
}

// ── INIT ──
renderWaveform(false);
renderRetentionBars([]);
updateSpeed(420);
loadArticles();

const storedStreak = parseInt(localStorage.getItem('speedai_streak') || '0');
$('streakCount').textContent = storedStreak;
const gp = Math.min(100, Math.round((storedStreak % 7) / 7 * 100));
$('goalPct').textContent = gp + '%';
$('goalBar').style.width = gp + '%';

const hist = JSON.parse(localStorage.getItem('speedai_history') || '[]');
if (hist.length) {
  const last = hist[hist.length-1];
  $('heroWpm').textContent = last.wpm;
  $('metricWpm').textContent = last.wpm;
  $('metricAcc').textContent = last.accuracy;
  $('metricRank').textContent = last.rank;
  renderRetentionBars(hist);
}
</script>
</body>
</html>"""

# ═══════════════════════════════════════════════════════════
# ADMIN PAGE  ( /admin )
# ═══════════════════════════════════════════════════════════
ADMIN_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>AI Speed Reader — Admin</title>
{{ shared_css }}
</head>
<body class="bg-brand-graybg text-slate-800 font-sans antialiased h-screen overflow-hidden flex">

<!-- Mobile overlay -->
<div id="overlay" class="overlay fixed inset-0 bg-slate-900/60 z-40" onclick="closeSidebar()"></div>

<!-- ══════════ SIDEBAR ══════════ -->
<aside id="sidebar"
  class="sidebar-drawer fixed lg:static top-0 left-0 bottom-0 w-[280px] bg-brand-dark
         flex flex-col shrink-0 z-50 shadow-xl">

  <div class="h-20 flex items-center px-8 border-b border-white/10">
    <div class="flex items-center gap-3">
      <div class="w-8 h-8 bg-brand-emerald rounded-lg flex items-center justify-center">
        <i class="fa-solid fa-bolt text-white text-sm"></i>
      </div>
      <span class="text-xl font-bold text-white tracking-tight">
        SpeedAI <span class="text-[10px] bg-brand-blue px-1.5 py-0.5 rounded ml-1 uppercase">Admin</span>
      </span>
    </div>
  </div>

  <nav class="flex-1 px-5 py-8 space-y-1.5 overflow-y-auto">
    <div class="px-4 mb-4 text-[10px] font-bold text-slate-500 uppercase tracking-widest">Main Menu</div>
    <a href="#" class="flex items-center gap-3 px-4 py-3 text-slate-400 hover:bg-white/5 hover:text-white rounded-xl transition-colors">
      <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-white/5"><i class="fa-solid fa-chart-pie text-sm"></i></div>
      <span class="font-medium text-sm">Overview</span>
    </a>
    <a href="#" class="flex items-center gap-3 px-4 py-3 bg-brand-blue text-white rounded-xl shadow-lg shadow-brand-blue/20">
      <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-white/20"><i class="fa-solid fa-spider text-sm"></i></div>
      <span class="font-medium text-sm ml-1">Content Crawler</span>
    </a>
    <a href="#" class="flex items-center gap-3 px-4 py-3 text-slate-400 hover:bg-white/5 hover:text-white rounded-xl transition-colors">
      <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-white/5"><i class="fa-solid fa-users text-sm"></i></div>
      <span class="font-medium text-sm">User Management</span>
    </a>
    <a href="#" class="flex items-center gap-3 px-4 py-3 text-slate-400 hover:bg-white/5 hover:text-white rounded-xl transition-colors">
      <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-white/5"><i class="fa-solid fa-layer-group text-sm"></i></div>
      <span class="font-medium text-sm">Learning Materials</span>
    </a>
    <div class="px-4 mt-8 mb-4 text-[10px] font-bold text-slate-500 uppercase tracking-widest">Settings</div>
    <a href="#" class="flex items-center gap-3 px-4 py-3 text-slate-400 hover:bg-white/5 hover:text-white rounded-xl transition-colors">
      <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-white/5"><i class="fa-solid fa-robot text-sm"></i></div>
      <span class="font-medium text-sm">AI Engine Config</span>
    </a>
  </nav>

  <div class="p-5 border-t border-white/10">
    <div class="flex items-center gap-3 px-2">
      <img src="https://storage.googleapis.com/uxpilot-auth.appspot.com/avatars/avatar-4.jpg"
           class="w-10 h-10 rounded-full border border-white/20" alt="">
      <div>
        <p class="text-xs font-bold text-white">System Admin</p>
        <p class="text-[10px] text-slate-500">Master Control</p>
      </div>
    </div>
  </div>
</aside>

<!-- ══════════ MAIN ══════════ -->
<main class="flex-1 flex flex-col min-w-0 overflow-hidden">

  <!-- Header -->
  <header class="h-20 px-4 lg:px-8 flex items-center justify-between border-b border-slate-200 bg-white shrink-0">
    <div class="flex items-center gap-3">
      <button onclick="openSidebar()" class="lg:hidden w-10 h-10 flex items-center justify-center rounded-xl bg-slate-50 border border-slate-200 text-slate-600">
        <i class="fa-solid fa-bars-staggered"></i>
      </button>
      <div>
        <h1 class="text-base lg:text-lg font-bold text-slate-900">Content Crawler Controller</h1>
        <p class="text-xs text-slate-500 hidden md:block">Manage news ingestion and article approval queue</p>
      </div>
    </div>
    <div class="flex items-center gap-3">
      <div class="flex items-center gap-2 px-3 py-1.5 bg-emerald-50 text-brand-emerald rounded-lg border border-emerald-100">
        <span class="w-1.5 h-1.5 bg-brand-emerald rounded-full animate-pulse"></span>
        <span class="text-[10px] font-bold uppercase tracking-wider hidden sm:block">Crawler Engine Online</span>
      </div>
      <a href="/" class="flex items-center gap-2 px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100 transition-colors">
        <i class="fa-solid fa-arrow-left"></i> Student View
      </a>
    </div>
  </header>

  <!-- Content -->
  <div class="flex-1 overflow-y-auto p-4 lg:p-8">
    <div class="max-w-[1200px] mx-auto space-y-8">

      <!-- SOURCE CONFIG -->
      <section class="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm">
        <div class="flex items-center gap-3 mb-6">
          <div class="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center text-brand-blue">
            <i class="fa-solid fa-filter text-sm"></i>
          </div>
          <h2 class="text-lg font-bold text-slate-900">Source Configuration</h2>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
          <div class="space-y-2">
            <label class="text-xs font-bold text-slate-500 uppercase tracking-wider">Target News Agency</label>
            <div class="relative">
              <select id="selSource" class="w-full pl-4 pr-10 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm appearance-none focus:outline-none focus:ring-2 focus:ring-brand-blue/20">
                <option>BBC News (Global)</option>
                <option>CNN International</option>
                <option>Reuters Technology</option>
                <option>All Sources</option>
              </select>
              <i class="fa-solid fa-chevron-down absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 text-xs pointer-events-none"></i>
            </div>
          </div>
          <div class="space-y-2">
            <label class="text-xs font-bold text-slate-500 uppercase tracking-wider">Content Category</label>
            <div class="relative">
              <select id="selCategory" class="w-full pl-4 pr-10 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm appearance-none focus:outline-none focus:ring-2 focus:ring-brand-blue/20">
                <option>Technology & AI</option>
                <option>Science & Nature</option>
                <option>Business & Finance</option>
                <option>World Politics</option>
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

      <!-- ARTICLE QUEUE -->
      <section class="space-y-5">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <h2 class="text-xl font-bold text-slate-900">Pending Article Queue</h2>
            <span id="queueBadge" class="px-2.5 py-0.5 bg-slate-200 text-slate-600 rounded-full text-xs font-bold">0 Articles</span>
          </div>
          <div class="flex items-center gap-2">
            <button onclick="selectAll()" class="px-4 py-2 bg-white border border-slate-200 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-50 transition-colors">Select All</button>
            <button onclick="batchApprove()" class="px-4 py-2 bg-brand-emerald text-white rounded-xl text-xs font-bold shadow-md shadow-brand-emerald/20 hover:bg-emerald-600 transition-colors">Batch Approve</button>
          </div>
        </div>
        <div id="queueList" class="space-y-4">
          <div class="bg-white rounded-2xl p-8 border border-slate-200 text-center text-slate-400">
            <i class="fa-solid fa-spider text-4xl mb-3 text-slate-200"></i>
            <p class="font-medium">Nhấn "RUN CRAWLER" để quét tin tức mới.</p>
          </div>
        </div>
      </section>

    </div>
  </div>

  <!-- Mobile bottom nav -->
  <nav class="lg:hidden fixed bottom-0 left-0 right-0 h-16 bg-white border-t border-slate-200 flex items-center justify-around px-6 z-30">
    <a href="#" class="flex flex-col items-center gap-1 text-brand-blue">
      <i class="fa-solid fa-spider text-lg"></i>
      <span class="text-[9px] font-bold uppercase">Crawler</span>
    </a>
    <a href="#" class="flex flex-col items-center gap-1 text-slate-400">
      <i class="fa-solid fa-layer-group text-lg"></i>
      <span class="text-[9px] font-bold uppercase">Library</span>
    </a>
    <a href="/" class="flex flex-col items-center gap-1 text-slate-400">
      <i class="fa-solid fa-users text-lg"></i>
      <span class="text-[9px] font-bold uppercase">Students</span>
    </a>
    <a href="#" class="flex flex-col items-center gap-1 text-slate-400">
      <i class="fa-solid fa-chart-line text-lg"></i>
      <span class="text-[9px] font-bold uppercase">Stats</span>
    </a>
  </nav>
</main>

<div id="toast" class="fixed bottom-20 lg:bottom-6 left-1/2 -translate-x-1/2 bg-brand-dark text-white px-5 py-3 rounded-xl text-sm shadow-xl opacity-0 pointer-events-none transition-all z-[100]"></div>

<script>
const $ = id => document.getElementById(id);
function openSidebar()  { $('sidebar').classList.add('open'); $('overlay').classList.add('show'); }
function closeSidebar() { $('sidebar').classList.remove('open'); $('overlay').classList.remove('show'); }

function showToast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.style.opacity = '1';
  setTimeout(() => t.style.opacity = '0', 2800);
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

let crawledArticles = [];
let selected = new Set();

function sourceBgAdmin(src) {
  const m = { BBC:'bg-red-500', CNN:'bg-red-600', Reuters:'bg-blue-600' };
  return m[src] || 'bg-slate-700';
}

async function runCrawler() {
  const btn = $('btnCrawl');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin text-xs"></i> Đang quét...';
  $('queueList').innerHTML = '<div class="bg-white rounded-2xl p-8 border border-slate-200 text-center text-slate-400"><i class="fa-solid fa-circle-notch fa-spin text-3xl mb-3"></i><p>Đang tải dữ liệu RSS...</p></div>';
  selected.clear();
  try {
    const res = await fetch('/api/crawl', { method: 'POST' });
    const data = await res.json();
    crawledArticles = data.articles || [];
    $('queueBadge').textContent = crawledArticles.length + ' Articles';
    renderQueue();
    showToast('✅ Quét xong ' + crawledArticles.length + ' bài báo');
  } catch(e) {
    $('queueList').innerHTML = '<div class="bg-white rounded-2xl p-8 border border-slate-200 text-center text-red-400"><i class="fa-solid fa-triangle-exclamation text-3xl mb-3"></i><p>Lỗi khi quét tin. Kiểm tra kết nối mạng.</p></div>';
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-play text-xs"></i> RUN CRAWLER / SCAN NEWS';
  }
}

function renderQueue() {
  if (!crawledArticles.length) {
    $('queueList').innerHTML = '<div class="bg-white rounded-2xl p-8 border border-slate-200 text-center text-slate-400"><p>Không tìm thấy bài phù hợp.</p></div>';
    return;
  }
  $('queueList').innerHTML = crawledArticles.map((a, idx) => {
    const sb = sourceBgAdmin(a.source);
    const dc = { Easy:'emerald', Medium:'yellow', Hard:'amber' }[a.difficulty||'Easy'] || 'emerald';
    return `
    <div class="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm flex flex-col md:flex-row items-start gap-5 hover:border-brand-blue/30 transition-colors group article-item" id="item-${idx}">
      <!-- Checkbox -->
      <div class="flex items-start gap-4 w-full md:w-auto">
        <input type="checkbox" onchange="toggleSelect(${idx})" class="mt-1.5 w-4 h-4 rounded text-brand-blue cursor-pointer">
        <!-- Thumbnail -->
        <div class="w-full md:w-48 h-32 rounded-xl overflow-hidden shrink-0 bg-slate-100 hidden md:block">
          <img src="${a.image||'https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=400&q=70'}"
               class="w-full h-full object-cover grayscale group-hover:grayscale-0 transition-all duration-500"
               onerror="this.src='https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=400&q=70'" alt="">
        </div>
      </div>
      <!-- Info -->
      <div class="flex-1 min-w-0 py-0.5 w-full">
        <div class="flex items-center gap-3 mb-2">
          <span class="px-2 py-0.5 ${sb} text-white text-[10px] font-bold rounded">${escHtml(a.source)}</span>
          <span class="text-[10px] font-bold text-${dc}-700 bg-${dc}-50 px-2 py-0.5 rounded">${a.difficulty||'Easy'}</span>
          <span class="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Crawled just now</span>
        </div>
        <h3 class="text-base font-bold text-slate-900 mb-2 leading-tight">${escHtml(a.title)}</h3>
        <p class="text-sm text-slate-500 line-clamp-2 leading-relaxed mb-3">${escHtml((a.content||'').slice(0,200))}...</p>
        <div class="flex items-center gap-4">
          <div class="flex items-center gap-1.5 text-xs text-slate-400"><i class="fa-solid fa-clock text-[10px]"></i> ${a.word_count||'--'} words</div>
          <div class="flex items-center gap-1.5 text-xs text-slate-400"><i class="fa-solid fa-signal text-[10px]"></i> ${a.difficulty||'Medium'}</div>
        </div>
      </div>
      <!-- Actions -->
      <div class="flex md:flex-col gap-2 shrink-0 w-full md:w-auto">
        <button onclick="approveOne(${idx}, this)"
                class="flex-1 md:flex-none px-5 py-2.5 bg-brand-emerald hover:bg-emerald-600 text-white rounded-xl text-xs font-bold shadow-md shadow-brand-emerald/10 transition-colors flex items-center justify-center gap-2">
          <i class="fa-solid fa-check"></i> APPROVE / DUYỆT BÀI
        </button>
        <button onclick="rejectOne(${idx})"
                class="flex-1 md:flex-none px-5 py-2.5 bg-slate-100 hover:bg-red-50 hover:text-red-600 text-slate-500 rounded-xl text-xs font-bold transition-colors flex items-center justify-center gap-2 border border-transparent hover:border-red-100">
          <i class="fa-solid fa-xmark"></i> REJECT / BỎ QUA
        </button>
      </div>
    </div>`;
  }).join('');
}

function toggleSelect(idx) { selected.has(idx) ? selected.delete(idx) : selected.add(idx); }

function selectAll() {
  const all = crawledArticles.map((_,i) => i);
  if (selected.size === all.length) { selected.clear(); }
  else { all.forEach(i => selected.add(i)); }
  document.querySelectorAll('.article-item input[type=checkbox]').forEach((cb, i) => { cb.checked = selected.has(i); });
}

async function approveOne(idx, btn) {
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Đang lưu...';
  try {
    const res = await fetch('/api/approve', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(crawledArticles[idx])
    });
    const data = await res.json();
    if (data.success) {
      btn.innerHTML = '<i class="fa-solid fa-check-double"></i> Đã duyệt';
      btn.className = btn.className.replace('bg-brand-emerald hover:bg-emerald-600','bg-slate-300');
      showToast(data.demo_mode ? '⚠️ Demo mode - chưa lưu vĩnh viễn' : '✅ Đã lưu vào Supabase');
    } else {
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-check"></i> APPROVE / DUYỆT BÀI';
      showToast('❌ Lỗi: ' + (data.error || 'Unknown'));
    }
  } catch(e) {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-check"></i> APPROVE / DUYỆT BÀI';
    showToast('❌ Không thể kết nối server');
  }
}

function rejectOne(idx) {
  const item = $('item-' + idx);
  if (item) { item.style.opacity = '0'; item.style.transform = 'translateX(40px)'; setTimeout(() => item.remove(), 300); }
  crawledArticles.splice(idx, 1);
  $('queueBadge').textContent = crawledArticles.length + ' Articles';
  setTimeout(renderQueue, 350);
}

async function batchApprove() {
  if (!selected.size) { showToast('⚠️ Chưa chọn bài nào!'); return; }
  const idxs = [...selected];
  let ok = 0;
  for (const i of idxs) {
    try {
      const res = await fetch('/api/approve', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(crawledArticles[i])
      });
      const d = await res.json();
      if (d.success) ok++;
    } catch(e) {}
  }
  showToast('✅ Đã duyệt ' + ok + '/' + idxs.length + ' bài báo');
  selected.clear();
  renderQueue();
}
</script>
</body>
</html>"""

# ═══════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════
@app.route("/")
def student_home():
    html_out = STUDENT_HTML.replace("{{ shared_css }}", SHARED_CSS)
    return render_template_string(html_out)

@app.route("/admin")
def admin_home():
    html_out = ADMIN_HTML.replace("{{ shared_css }}", SHARED_CSS)
    return render_template_string(html_out)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
