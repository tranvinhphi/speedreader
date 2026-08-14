# -*- coding: utf-8 -*-
"""
============================================================
  AI ENGLISH SPEED READER
  Ứng dụng luyện đọc tiếng Anh tốc độ cao cho học sinh,
  sử dụng Web Speech API để nhận diện giọng nói + chấm điểm
  tự động (WPM, độ chính xác, xếp hạng).

  Backend : Flask + feedparser (crawl RSS) + Supabase (lưu trữ)
  Frontend: HTML/CSS/JS thuần, nhúng dạng chuỗi trong Flask,
            thiết kế Mobile-first, Responsive cho PC/iPhone/iPad.

  Cách chạy local:
      pip install -r requirements.txt
      export SUPABASE_URL="https://xxxx.supabase.co"
      export SUPABASE_KEY="xxxxxxxx"
      python app.py

  Deploy Render: xem hướng dẫn trong README.md
============================================================
"""

import os
import re
import html
from datetime import datetime, timezone

import feedparser
from flask import Flask, jsonify, request, render_template_string

# supabase-py là thư viện tùy chọn: nếu chưa cấu hình biến môi trường,
# ứng dụng vẫn chạy được ở chế độ "demo" (không lưu trữ vĩnh viễn).
try:
    from supabase import create_client, Client
except ImportError:  # pragma: no cover
    create_client = None
    Client = None

app = Flask(__name__)

# ============================================================
# PHẦN 1: BACKEND - CẤU HÌNH & KẾT NỐI SUPABASE
# ============================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

supabase = None
if SUPABASE_URL and SUPABASE_KEY and create_client is not None:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:  # pragma: no cover
        print(f"[CẢNH BÁO] Không thể kết nối Supabase: {e}")
        supabase = None
else:
    print("[THÔNG BÁO] Chưa cấu hình SUPABASE_URL/SUPABASE_KEY - "
          "ứng dụng chạy ở chế độ DEMO (không lưu trữ vĩnh viễn).")

# Tên 2 bảng cần tạo sẵn trong Supabase (xem SQL mẫu trong README.md)
TABLE_ARTICLES = "articles"   # id, title, source, url, content, created_at
TABLE_SCORES = "scores"       # id, student_name, article_title, wpm, accuracy, rank, created_at

# Dữ liệu mẫu dùng khi chưa cấu hình Supabase, để giao diện luôn có bài đọc thử
DEMO_ARTICLES = [
    {
        "id": "demo-1",
        "source": "BBC: AI Transforms Tech",
        "title": "Artificial Intelligence Is Reshaping the Technology Industry",
        "content": (
            "Artificial intelligence is transforming the landscape of global "
            "technology. Companies across every sector are racing to adopt "
            "machine learning tools that can analyze data, automate tasks, "
            "and generate new ideas faster than ever before. However, "
            "experts warn that this rapid change also brings new challenges "
            "around privacy, jobs, and fairness that society must address "
            "together."
        ),
        "url": "",
    },
    {
        "id": "demo-2",
        "source": "CNN: Climate Change Crisis",
        "title": "Global Leaders Debate the Future of Climate Policy",
        "content": (
            "Climate change continues to affect communities around the "
            "world, from rising sea levels to extreme weather events. "
            "Scientists say that reducing carbon emissions quickly is "
            "essential to prevent long term damage. Governments are now "
            "under pressure to invest in clean energy and support "
            "countries that are most vulnerable to these changes."
        ),
        "url": "",
    },
    {
        "id": "demo-3",
        "source": "Reuters: Global Markets",
        "title": "Investors Watch Global Markets Amid Economic Uncertainty",
        "content": (
            "Global markets moved cautiously this week as investors "
            "weighed new economic data against ongoing uncertainty in "
            "trade policy. Analysts believe that steady growth is still "
            "possible if central banks manage interest rates carefully. "
            "Many traders are choosing to wait for clearer signals before "
            "making major decisions."
        ),
        "url": "",
    },
]

# Danh sách nguồn RSS quốc tế dùng để quét tin mới ở trang Admin
RSS_FEEDS = {
    "BBC: AI Transforms Tech": "http://feeds.bbci.co.uk/news/technology/rss.xml",
    "BBC: World News": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "CNN: Climate Change Crisis": "http://rss.cnn.com/rss/cnn_topstories.rss",
    "Reuters: Global Markets": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
}


def clean_html_text(raw_html: str) -> str:
    """Loại bỏ thẻ HTML và giải mã ký tự đặc biệt từ nội dung RSS."""
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def calc_rank(wpm: float, accuracy: float) -> str:
    """Xếp hạng học sinh dựa trên tốc độ đọc (WPM) và độ chính xác (%)."""
    if accuracy >= 95 and wpm >= 130:
        return "S"
    if accuracy >= 90 and wpm >= 100:
        return "A"
    if accuracy >= 80 and wpm >= 70:
        return "B"
    return "C"


# ============================================================
# PHẦN 1: BACKEND - CÁC API
# ============================================================

@app.route("/api/crawl", methods=["POST"])
def api_crawl():
    """Quét tin mới từ các nguồn RSS quốc tế, trả về danh sách bài (chưa lưu)."""
    found = []
    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:6]:
                title = clean_html_text(entry.get("title", ""))
                summary = clean_html_text(
                    entry.get("summary", entry.get("description", ""))
                )
                link = entry.get("link", "")
                # Chỉ lấy bài có nội dung đủ dài để luyện đọc (>= 25 từ)
                if len(summary.split()) < 25:
                    continue
                found.append({
                    "source": source_name,
                    "title": title,
                    "content": summary,
                    "url": link,
                })
        except Exception as e:
            print(f"[LỖI CRAWL] {source_name}: {e}")
            continue

    return jsonify({"success": True, "count": len(found), "articles": found})


@app.route("/api/approve", methods=["POST"])
def api_approve():
    """Duyệt 1 bài báo do Admin chọn, lưu vào Supabase."""
    data = request.get_json(force=True, silent=True) or {}
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()

    if not title or not content:
        return jsonify({"success": False, "error": "Thiếu tiêu đề hoặc nội dung bài báo."}), 400

    record = {
        "title": title,
        "source": data.get("source", ""),
        "url": data.get("url", ""),
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if supabase is None:
        # Chế độ demo: xác nhận thành công giả lập, không lưu vĩnh viễn
        return jsonify({
            "success": True,
            "demo_mode": True,
            "message": "Chưa cấu hình Supabase - bài báo KHÔNG được lưu vĩnh viễn (chế độ demo).",
            "data": record,
        })

    try:
        res = supabase.table(TABLE_ARTICLES).insert(record).execute()
        return jsonify({"success": True, "data": res.data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/articles", methods=["GET"])
def api_articles():
    """Lấy danh sách bài báo đã được duyệt, hiển thị cho học sinh chọn."""
    if supabase is None:
        return jsonify({"success": True, "demo_mode": True, "articles": DEMO_ARTICLES})

    try:
        res = (
            supabase.table(TABLE_ARTICLES)
            .select("*")
            .order("created_at", desc=True)
            .limit(30)
            .execute()
        )
        articles = res.data or []
        if not articles:
            # Nếu Supabase chưa có bài nào, vẫn cho học sinh luyện với bài demo
            return jsonify({"success": True, "demo_mode": True, "articles": DEMO_ARTICLES})
        return jsonify({"success": True, "articles": articles})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "articles": DEMO_ARTICLES})


@app.route("/api/save_score", methods=["POST"])
def api_save_score():
    """Lưu kết quả luyện đọc (WPM, độ chính xác, xếp hạng) của học sinh."""
    data = request.get_json(force=True, silent=True) or {}
    student_name = (data.get("student_name") or "").strip()

    if not student_name:
        return jsonify({"success": False, "error": "Thiếu tên học sinh."}), 400

    record = {
        "student_name": student_name,
        "article_title": data.get("article_title", ""),
        "wpm": data.get("wpm", 0),
        "accuracy": data.get("accuracy", 0),
        "rank": data.get("rank", "C"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if supabase is None:
        return jsonify({
            "success": True,
            "demo_mode": True,
            "message": "Chưa cấu hình Supabase - điểm số KHÔNG được lưu vĩnh viễn (chế độ demo).",
            "data": record,
        })

    try:
        res = supabase.table(TABLE_SCORES).insert(record).execute()
        return jsonify({"success": True, "data": res.data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# PHẦN 2: FRONTEND - CSS DÙNG CHUNG (Mobile-first, Responsive)
# ============================================================

BASE_CSS = """
:root{
  --navy:#1e2a44;
  --navy-light:#27395c;
  --blue:#2563eb;
  --blue-dark:#1d4ed8;
  --green:#16a34a;
  --green-bg:#dcfce7;
  --bg:#eef1f6;
  --card:#ffffff;
  --text:#1f2937;
  --muted:#6b7280;
  --border:#e2e8f0;
  --radius:14px;
  --shadow:0 10px 30px rgba(30,42,68,0.08);
}
*{box-sizing:border-box;}
html,body{margin:0;padding:0;}
body{
  font-family:'Inter','Segoe UI',system-ui,-apple-system,sans-serif;
  background:var(--bg);
  color:var(--text);
  line-height:1.5;
  -webkit-font-smoothing:antialiased;
}
.header{
  background:linear-gradient(135deg,var(--navy),var(--navy-light));
  color:#fff;
  padding:14px 16px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  flex-wrap:wrap;
  gap:8px;
  box-shadow:0 2px 12px rgba(0,0,0,0.15);
  position:sticky;
  top:0;
  z-index:50;
}
.header .brand{
  display:flex;align-items:center;gap:10px;
  font-weight:700;font-size:18px;
}
.header .brand .dot{
  width:34px;height:34px;border-radius:10px;
  background:rgba(255,255,255,0.12);
  display:flex;align-items:center;justify-content:center;
  font-size:18px;
}
.header .meta{
  display:flex;align-items:center;gap:14px;
  font-size:13px;color:#cbd5e1;
}
.header .meta a{color:#cbd5e1;text-decoration:none;}
.header .meta a:hover{color:#fff;}

.container{
  max-width:900px;
  margin:0 auto;
  padding:16px 15px 60px;
}
.card{
  background:var(--card);
  border-radius:var(--radius);
  box-shadow:var(--shadow);
  padding:20px;
  margin-bottom:18px;
  border:1px solid var(--border);
}
.card h2{
  font-size:16px;
  margin:0 0 14px 0;
  display:flex;align-items:center;gap:8px;
  color:var(--navy);
}
.input-field{
  width:100%;
  padding:13px 14px;
  border-radius:10px;
  border:1.5px solid var(--border);
  font-size:16px;
  font-family:inherit;
  margin-bottom:12px;
  min-height:48px;
  transition:border-color .2s;
}
.input-field:focus{outline:none;border-color:var(--blue);}

.article-grid{
  display:grid;
  grid-template-columns:1fr;
  gap:10px;
  margin-bottom:16px;
}
@media(min-width:640px){
  .article-grid{grid-template-columns:repeat(3,1fr);}
}
.article-chip{
  border:1.5px solid var(--border);
  background:#f8fafc;
  border-radius:10px;
  padding:14px 12px;
  min-height:48px;
  display:flex;
  align-items:center;
  gap:10px;
  cursor:pointer;
  font-size:14px;
  font-weight:600;
  transition:all .2s;
  user-select:none;
}
.article-chip:hover{border-color:var(--blue);background:#eff6ff;}
.article-chip.selected{
  border-color:var(--blue);
  background:#dbeafe;
  color:var(--blue-dark);
  box-shadow:0 2px 8px rgba(37,99,235,0.2);
}
.article-chip .box{
  width:18px;height:18px;border-radius:5px;
  border:2px solid #cbd5e1;flex:none;
  display:flex;align-items:center;justify-content:center;
  background:#fff;font-size:11px;
}
.article-chip.selected .box{
  background:var(--blue);border-color:var(--blue);color:#fff;
}

.btn{
  display:flex;align-items:center;justify-content:center;gap:8px;
  width:100%;
  min-height:48px;
  border:none;
  border-radius:10px;
  font-size:16px;
  font-weight:700;
  font-family:inherit;
  cursor:pointer;
  transition:transform .15s, box-shadow .2s, background .2s;
}
.btn:active{transform:scale(0.98);}
.btn-primary{
  background:linear-gradient(135deg,var(--blue),var(--blue-dark));
  color:#fff;
  box-shadow:0 6px 18px rgba(37,99,235,0.35);
}
.btn-primary:hover{box-shadow:0 8px 22px rgba(37,99,235,0.45);}
.btn-primary:disabled{
  background:#94a3b8;box-shadow:none;cursor:not-allowed;
}
.btn-danger{
  background:#fff;
  color:#dc2626;
  border:1.5px solid #fecaca;
}
.btn-danger:hover{background:#fef2f2;}
.btn-ghost{
  background:#f1f5f9;
  color:var(--navy);
  border:1.5px solid var(--border);
}
.btn-ghost:hover{background:#e2e8f0;}
.btn-row{display:flex;gap:10px;margin-top:10px;}

.reading-box{
  background:#fbfdff;
  border:1.5px solid var(--border);
  border-radius:12px;
  padding:20px;
  font-size:22px;
  line-height:2;
  max-height:340px;
  overflow-y:auto;
  scroll-behavior:smooth;
}
@media(min-width:640px){
  .reading-box{font-size:24px;}
}
@media(min-width:900px){
  .reading-box{font-size:26px;}
}
.reading-box .placeholder{color:var(--muted);font-size:16px;line-height:1.6;}
.word{
  transition:all .3s ease;
  border-radius:5px;
  padding:1px 2px;
}
.word.current{
  background:#fef9c3;
}
.word.read{
  background:var(--green-bg);
  color:var(--green);
  font-weight:700;
}

.mic-status{
  display:flex;align-items:center;gap:8px;
  font-size:13px;color:var(--muted);
  margin-top:10px;
}
.mic-dot{
  width:9px;height:9px;border-radius:50%;background:#cbd5e1;
}
.mic-dot.live{
  background:#ef4444;
  animation:pulse 1.2s infinite;
}
@keyframes pulse{
  0%{box-shadow:0 0 0 0 rgba(239,68,68,0.5);}
  70%{box-shadow:0 0 0 9px rgba(239,68,68,0);}
  100%{box-shadow:0 0 0 0 rgba(239,68,68,0);}
}

.result-box{
  display:none;
  background:linear-gradient(135deg,#0f2440,var(--navy-light));
  color:#fff;
  border-radius:var(--radius);
  padding:22px;
  box-shadow:0 14px 34px rgba(15,36,64,0.35);
}
.result-box.show{display:block;animation:fadeUp .4s ease;}
@keyframes fadeUp{
  from{opacity:0;transform:translateY(10px);}
  to{opacity:1;transform:translateY(0);}
}
.result-box h2{color:#fff;}
.result-grid{
  display:grid;
  grid-template-columns:repeat(3,1fr);
  gap:10px;
  text-align:center;
}
.result-grid .stat-value{font-size:26px;font-weight:800;}
.result-grid .stat-label{font-size:12px;color:#cbd5e1;margin-top:2px;}
.rank-badge{
  display:inline-flex;align-items:center;justify-content:center;
  width:44px;height:44px;border-radius:50%;
  font-size:20px;font-weight:800;
  background:#facc15;color:#78350f;
}

.empty-state{
  text-align:center;color:var(--muted);
  padding:30px 10px;font-size:14px;
}

/* ------- Trang Admin ------- */
.admin-list{display:flex;flex-direction:column;gap:12px;}
.admin-item{
  border:1.5px solid var(--border);
  border-radius:12px;
  padding:14px;
  background:#f8fafc;
}
.admin-item .src{
  font-size:12px;color:var(--blue-dark);font-weight:700;
  text-transform:uppercase;letter-spacing:.03em;
}
.admin-item h3{margin:6px 0;font-size:15px;color:var(--navy);}
.admin-item p{margin:0 0 10px 0;font-size:13.5px;color:var(--muted);}
.admin-item .btn{width:auto;padding:0 18px;}
.toast{
  position:fixed;bottom:20px;left:50%;transform:translateX(-50%);
  background:var(--navy);color:#fff;padding:12px 20px;border-radius:10px;
  font-size:14px;box-shadow:0 10px 25px rgba(0,0,0,0.25);
  opacity:0;pointer-events:none;transition:opacity .3s, transform .3s;
  z-index:200;
}
.toast.show{opacity:1;transform:translateX(-50%) translateY(-6px);}
.spinner{
  width:16px;height:16px;border-radius:50%;
  border:2.5px solid rgba(255,255,255,0.4);border-top-color:#fff;
  animation:spin .7s linear infinite;
}
@keyframes spin{to{transform:rotate(360deg);}}
"""


# ============================================================
# PHẦN 2: FRONTEND - TRANG HỌC SINH  ( / )
# ============================================================

STUDENT_PAGE = """
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1">
<title>AI Speed Reader</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>{{ css }}</style>
</head>
<body>

<div class="header">
  <div class="brand"><span class="dot">🎙️</span> AI Speed Reader</div>
  <div class="meta">
    <span id="studentTag">👤 Học sinh: <b id="studentNameTag">--</b></span>
    <a href="/admin">⚙️ Admin</a>
  </div>
</div>

<div class="container">

  <div class="card">
    <h2>🙋 Thông tin học sinh</h2>
    <input id="studentName" class="input-field" type="text"
           placeholder="Nhập tên của bạn (VD: Alex Nguyen)">
  </div>

  <div class="card">
    <h2>📚 Chọn bài đọc (Reading Selection)</h2>
    <div id="articleGrid" class="article-grid">
      <div class="empty-state">Đang tải danh sách bài báo...</div>
    </div>
    <button id="btnStart" class="btn btn-primary" disabled>
      🎤 Bắt đầu đọc (Start Reading)
    </button>
    <div class="mic-status">
      <span id="micDot" class="mic-dot"></span>
      <span id="micStatusText">Micro chưa hoạt động</span>
    </div>
    <div class="btn-row" id="controlRow" style="display:none;">
      <button id="btnStop" class="btn btn-danger">⏹ Dừng &amp; xem kết quả</button>
      <button id="btnReset" class="btn btn-ghost">↺ Đọc lại</button>
    </div>
  </div>

  <div class="card">
    <h2>📝 Khu vực luyện đọc (Reading Area)</h2>
    <div id="readingBox" class="reading-box">
      <div class="placeholder">Hãy chọn một bài báo và nhấn "Bắt đầu đọc" để luyện tập. Văn bản sẽ hiển thị tại đây, từ nào bạn đọc đúng sẽ tự động chuyển sang màu xanh lá.</div>
    </div>
  </div>

  <div id="resultBox" class="result-box card">
    <h2>📊 Kết quả (Results)</h2>
    <div class="result-grid">
      <div>
        <div class="stat-value" id="resWpm">0</div>
        <div class="stat-label">Tốc độ (WPM)</div>
      </div>
      <div>
        <div class="stat-value" id="resAcc">0%</div>
        <div class="stat-label">Độ chính xác</div>
      </div>
      <div>
        <span class="rank-badge" id="resRank">C</span>
        <div class="stat-label">Xếp hạng</div>
      </div>
    </div>
  </div>

</div>

<div id="toast" class="toast"></div>

<script>
// ============================================================
// STATE CHUNG CỦA ỨNG DỤNG
// ============================================================
let articles = [];
let selectedArticle = null;
let words = [];          // mảng các từ (đã làm sạch) của bài đọc
let matchIndex = 0;      // vị trí từ tiếp theo cần đọc đúng
let spokenCount = 0;     // tổng số từ đã nhận diện được từ micro
let correctCount = 0;    // tổng số từ đọc đúng
let startTime = null;
let recognition = null;
let isListening = false;

const $ = (id) => document.getElementById(id);

function showToast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2600);
}

function normalizeWord(w) {
  return (w || "").toLowerCase().replace(/[^a-z0-9']/g, "");
}

// ============================================================
// TẢI DANH SÁCH BÀI BÁO TỪ BACKEND (/api/articles)
// ============================================================
async function loadArticles() {
  try {
    const res = await fetch("/api/articles");
    const data = await res.json();
    articles = data.articles || [];
  } catch (e) {
    articles = [];
  }
  renderArticleGrid();
}

function renderArticleGrid() {
  const grid = $("articleGrid");
  if (!articles.length) {
    grid.innerHTML = '<div class="empty-state">Chưa có bài báo nào được duyệt. Vui lòng vào trang Admin để quét &amp; duyệt tin.</div>';
    return;
  }
  grid.innerHTML = "";
  articles.forEach((a, idx) => {
    const chip = document.createElement("div");
    chip.className = "article-chip";
    chip.dataset.idx = idx;
    chip.innerHTML = `<span class="box"></span><span>${escapeHtml(a.source || "Bài đọc")}</span>`;
    chip.addEventListener("click", () => selectArticle(idx));
    grid.appendChild(chip);
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function selectArticle(idx) {
  selectedArticle = articles[idx];
  document.querySelectorAll(".article-chip").forEach((el) => {
    el.classList.toggle("selected", Number(el.dataset.idx) === idx);
  });
  document.querySelectorAll(".article-chip .box").forEach((b) => (b.textContent = ""));
  const selEl = document.querySelector(`.article-chip[data-idx="${idx}"] .box`);
  if (selEl) selEl.textContent = "✓";
  $("btnStart").disabled = false;
}

// ============================================================
// KHỞI TẠO WEB SPEECH API (NHẬN DIỆN GIỌNG NÓI)
// ============================================================
function getSpeechRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return null;
  const r = new SR();
  r.lang = "en-US";
  r.continuous = true;
  r.interimResults = true;
  return r;
}

function buildReadingBox() {
  const box = $("readingBox");
  box.innerHTML = "";
  words.forEach((w, i) => {
    const span = document.createElement("span");
    span.className = "word";
    span.id = "word-" + i;
    span.textContent = w.display + " ";
    box.appendChild(span);
  });
  const first = $("word-0");
  if (first) first.classList.add("current");
}

function markWordRead(i) {
  const el = $("word-" + i);
  if (!el) return;
  el.classList.remove("current");
  el.classList.add("read");
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  const next = $("word-" + (i + 1));
  if (next) next.classList.add("current");
}

// ============================================================
// XỬ LÝ SỰ KIỆN NHẬN DIỆN GIỌNG NÓI -> SO KHỚP TỪNG TỪ
// ============================================================
function handleRecognitionResult(event) {
  let transcript = "";
  for (let i = event.resultIndex; i < event.results.length; i++) {
    transcript += " " + event.results[i][0].transcript;
  }
  const spokenWords = transcript.trim().split(/\\s+/).map(normalizeWord).filter(Boolean);

  spokenWords.forEach((sw) => {
    if (matchIndex >= words.length) return;
    spokenCount++;
    if (sw === words[matchIndex].clean) {
      correctCount++;
      markWordRead(matchIndex);
      matchIndex++;
    }
  });

  if (matchIndex >= words.length) {
    finishReading();
  }
}

function startReading() {
  if (!selectedArticle) return;
  const studentName = $("studentName").value.trim();
  if (!studentName) {
    showToast("⚠️ Vui lòng nhập tên học sinh trước khi bắt đầu.");
    return;
  }
  $("studentNameTag").textContent = studentName;

  recognition = getSpeechRecognition();
  if (!recognition) {
    showToast("❌ Trình duyệt không hỗ trợ Web Speech API. Hãy dùng Chrome trên máy tính hoặc Android.");
    return;
  }

  const raw = (selectedArticle.content || "").trim().split(/\\s+/);
  words = raw.map((w) => ({ display: w, clean: normalizeWord(w) })).filter((w) => w.clean);

  matchIndex = 0;
  spokenCount = 0;
  correctCount = 0;
  buildReadingBox();
  $("resultBox").classList.remove("show");

  recognition.onresult = handleRecognitionResult;
  recognition.onerror = (e) => {
    console.warn("Speech recognition error:", e.error);
  };
  recognition.onend = () => {
    isListening = false;
    $("micDot").classList.remove("live");
    $("micStatusText").textContent = "Micro đã dừng";
  };

  recognition.start();
  isListening = true;
  startTime = performance.now();
  $("micDot").classList.add("live");
  $("micStatusText").textContent = "Đang nghe... hãy đọc to bài báo";
  $("btnStart").disabled = true;
  $("controlRow").style.display = "flex";
}

function stopRecognition() {
  if (recognition && isListening) {
    recognition.stop();
  }
}

function finishReading() {
  stopRecognition();
  const elapsedMinutes = Math.max((performance.now() - startTime) / 60000, 0.05);
  const wpm = Math.round(matchIndex / elapsedMinutes);
  const accuracy = spokenCount > 0 ? Math.round((correctCount / spokenCount) * 100) : 0;
  const rank = calcRank(wpm, accuracy);

  $("resWpm").textContent = wpm;
  $("resAcc").textContent = accuracy + "%";
  const rankEl = $("resRank");
  rankEl.textContent = rank;
  rankEl.style.background = rankColor(rank);
  $("resultBox").classList.add("show");
  $("resultBox").scrollIntoView({ behavior: "smooth", block: "center" });
  $("btnStart").disabled = false;
  $("controlRow").style.display = "none";

  saveScore(wpm, accuracy, rank);
}

function calcRank(wpm, accuracy) {
  if (accuracy >= 95 && wpm >= 130) return "S";
  if (accuracy >= 90 && wpm >= 100) return "A";
  if (accuracy >= 80 && wpm >= 70) return "B";
  return "C";
}

function rankColor(rank) {
  return { S: "#facc15", A: "#4ade80", B: "#60a5fa", C: "#f87171" }[rank] || "#facc15";
}

async function saveScore(wpm, accuracy, rank) {
  try {
    await fetch("/api/save_score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        student_name: $("studentName").value.trim(),
        article_title: selectedArticle.title || selectedArticle.source,
        wpm, accuracy, rank,
      }),
    });
  } catch (e) {
    console.warn("Không thể lưu điểm:", e);
  }
}

function resetReading() {
  stopRecognition();
  words = [];
  matchIndex = 0;
  $("readingBox").innerHTML = '<div class="placeholder">Hãy chọn một bài báo và nhấn "Bắt đầu đọc" để luyện tập.</div>';
  $("resultBox").classList.remove("show");
  $("controlRow").style.display = "none";
  $("btnStart").disabled = !selectedArticle;
  $("micStatusText").textContent = "Micro chưa hoạt động";
}

$("btnStart").addEventListener("click", startReading);
$("btnStop").addEventListener("click", finishReading);
$("btnReset").addEventListener("click", resetReading);

loadArticles();
</script>
</body>
</html>
"""


# ============================================================
# PHẦN 2: FRONTEND - TRANG ADMIN  ( /admin )
# ============================================================

ADMIN_PAGE = """
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1">
<title>AI Speed Reader - Admin</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>{{ css }}</style>
</head>
<body>

<div class="header">
  <div class="brand"><span class="dot">⚙️</span> AI Speed Reader - Admin</div>
  <div class="meta"><a href="/">🎙️ Về trang học sinh</a></div>
</div>

<div class="container">

  <div class="card">
    <h2>📰 Quét tin tức quốc tế (RSS)</h2>
    <p style="color:var(--muted);font-size:13.5px;margin-top:-6px;">
      Quét từ BBC, CNN, Reuters... để lấy bài báo mới nhất, sau đó chọn bài phù hợp và bấm "Duyệt" để lưu vào Supabase cho học sinh luyện đọc.
    </p>
    <button id="btnCrawl" class="btn btn-primary">🔍 Quét tin mới</button>
  </div>

  <div class="card">
    <h2>🗂️ Danh sách bài quét được</h2>
    <div id="crawlList" class="admin-list">
      <div class="empty-state">Nhấn "Quét tin mới" để bắt đầu.</div>
    </div>
  </div>

</div>

<div id="toast" class="toast"></div>

<script>
const $ = (id) => document.getElementById(id);

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function showToast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2600);
}

async function crawlNews() {
  const btn = $("btnCrawl");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Đang quét...';
  $("crawlList").innerHTML = '<div class="empty-state">Đang tải dữ liệu từ RSS...</div>';

  try {
    const res = await fetch("/api/crawl", { method: "POST" });
    const data = await res.json();
    renderCrawlList(data.articles || []);
    showToast(`✅ Đã quét được ${data.count || 0} bài báo.`);
  } catch (e) {
    $("crawlList").innerHTML = '<div class="empty-state">❌ Lỗi khi quét tin. Vui lòng thử lại.</div>';
  } finally {
    btn.disabled = false;
    btn.innerHTML = "🔍 Quét tin mới";
  }
}

function renderCrawlList(list) {
  const box = $("crawlList");
  if (!list.length) {
    box.innerHTML = '<div class="empty-state">Không tìm thấy bài báo phù hợp.</div>';
    return;
  }
  box.innerHTML = "";
  list.forEach((a, idx) => {
    const item = document.createElement("div");
    item.className = "admin-item";
    item.innerHTML = `
      <div class="src">${escapeHtml(a.source)}</div>
      <h3>${escapeHtml(a.title)}</h3>
      <p>${escapeHtml(a.content.slice(0, 180))}...</p>
      <button class="btn btn-primary" data-idx="${idx}">✅ Duyệt bài này</button>
    `;
    item.querySelector("button").addEventListener("click", (e) => approveArticle(a, e.target));
    box.appendChild(item);
  });
  window.__crawledArticles = list;
}

async function approveArticle(article, btnEl) {
  btnEl.disabled = true;
  btnEl.textContent = "Đang lưu...";
  try {
    const res = await fetch("/api/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(article),
    });
    const data = await res.json();
    if (data.success) {
      btnEl.textContent = "✔ Đã duyệt";
      btnEl.style.background = "#16a34a";
      showToast(data.demo_mode
        ? "⚠️ Đã duyệt (chế độ demo - chưa cấu hình Supabase)."
        : "✅ Đã lưu bài báo vào Supabase.");
    } else {
      btnEl.disabled = false;
      btnEl.textContent = "✅ Duyệt bài này";
      showToast("❌ Lỗi: " + (data.error || "Không rõ nguyên nhân"));
    }
  } catch (e) {
    btnEl.disabled = false;
    btnEl.textContent = "✅ Duyệt bài này";
    showToast("❌ Không thể kết nối máy chủ.");
  }
}

$("btnCrawl").addEventListener("click", crawlNews);
</script>
</body>
</html>
"""


# ============================================================
# PHẦN 1: BACKEND - 2 ROUTE GIAO DIỆN
# ============================================================

@app.route("/")
def student_home():
    """Khu vực học sinh: chọn bài, luyện đọc, xem kết quả."""
    return render_template_string(STUDENT_PAGE, css=BASE_CSS)


@app.route("/admin")
def admin_home():
    """Khu vực quản lý: quét tin RSS, duyệt bài đăng cho học sinh."""
    return render_template_string(ADMIN_PAGE, css=BASE_CSS)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
