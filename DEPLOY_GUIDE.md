# 🚀 Hướng dẫn Deploy AI Speed Reader lên Internet

## ❌ Netlify KHÔNG phù hợp

Netlify chỉ host **static files** (HTML/CSS/JS thuần).  
App này dùng **Python Flask** — cần một server Python thật chạy liên tục.

---

## ✅ CÁC LỰA CHỌN MIỄN PHÍ PHÙ HỢP

### 🥇 Lựa chọn 1: Render.com (KHUYẾN NGHỊ — Miễn phí)

**Ưu điểm:** Dễ nhất, miễn phí, hỗ trợ Flask hoàn hảo, auto-deploy từ GitHub.

#### Các bước:

**Bước 1: Đẩy code lên GitHub**
```bash
# Tạo repo mới trên github.com rồi chạy:
cd AIEnglishspeedreader
git remote add origin https://github.com/TÊN_BẠN/ai-speed-reader.git
git branch -M main
git push -u origin main
```

**Bước 2: Tạo Web Service trên Render**
1. Vào https://render.com → Đăng ký miễn phí
2. Click **"New +"** → **"Web Service"**
3. Kết nối GitHub → chọn repo `ai-speed-reader`
4. Cấu hình:
   - **Name:** `ai-speed-reader` (hoặc tên bạn muốn)
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Instance Type:** `Free`

**Bước 3: Thêm biến môi trường Supabase**
Vào tab **"Environment"** → Add:
```
SUPABASE_URL  = https://xxxx.supabase.co
SUPABASE_KEY  = eyJhbGciOi...
```

**Bước 4: Deploy!**
- Click **"Create Web Service"**
- Chờ ~3 phút build xong
- URL của bạn: `https://ai-speed-reader.onrender.com`

> ⚠️ **Lưu ý Free tier:** Server sẽ "ngủ" sau 15 phút không dùng.  
> Lần đầu truy cập sẽ chờ ~30 giây để "thức dậy". Đây là bình thường.

---

### 🥈 Lựa chọn 2: Railway.app (Miễn phí $5 credit/tháng)

1. Vào https://railway.app → Đăng ký
2. **"New Project"** → **"Deploy from GitHub repo"**
3. Chọn repo → Railway tự detect Python
4. Add biến môi trường `SUPABASE_URL` và `SUPABASE_KEY`
5. Deploy tự động!

---

### 🥉 Lựa chọn 3: PythonAnywhere (Miễn phí vĩnh viễn, chậm hơn)

1. Vào https://www.pythonanywhere.com → Đăng ký free
2. Tab **"Web"** → **"Add a new web app"** → Flask
3. Upload file `app.py` vào thư mục
4. Cấu hình WSGI, cài requirements
5. URL: `TÊN_BẠN.pythonanywhere.com`

---

## 🗄️ Cấu hình Supabase (Database)

### Tạo bảng (chạy SQL trong Supabase Dashboard → SQL Editor):

```sql
-- Bảng bài báo đã duyệt
CREATE TABLE IF NOT EXISTS articles (
    id bigint generated always as identity primary key,
    title text not null,
    source text,
    url text,
    content text not null,
    difficulty text default 'Medium',
    image text,
    read_time text,
    created_at timestamptz default now()
);

-- Bảng điểm số học sinh  
CREATE TABLE IF NOT EXISTS scores (
    id bigint generated always as identity primary key,
    student_name text not null,
    article_title text,
    wpm integer default 0,
    accuracy integer default 0,
    rank text default 'C',
    created_at timestamptz default now()
);

-- Cho phép đọc/ghi công khai
ALTER TABLE articles ENABLE ROW LEVEL SECURITY;
ALTER TABLE scores ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public read articles" ON articles FOR SELECT USING (true);
CREATE POLICY "public insert articles" ON articles FOR INSERT WITH CHECK (true);
CREATE POLICY "public read scores" ON scores FOR SELECT USING (true);
CREATE POLICY "public insert scores" ON scores FOR INSERT WITH CHECK (true);
```

### Lấy API Keys:
Vào **Supabase Dashboard → Project Settings → API**:
- `SUPABASE_URL` = Project URL (dạng `https://xxxx.supabase.co`)
- `SUPABASE_KEY` = `anon` / `public` key

---

## 📁 Cấu trúc file cần upload lên GitHub

```
AIEnglishspeedreader/
├── app.py              ← Toàn bộ Flask app
├── requirements.txt    ← Thư viện Python
├── Procfile            ← Lệnh start cho Render/Railway
├── runtime.txt         ← Phiên bản Python
├── README.md
├── CHANGELOG.md
└── DEPLOY_GUIDE.md     ← File này
```

---

## 🌐 Sau khi deploy xong

| URL | Chức năng |
|-----|-----------|
| `https://your-app.onrender.com/` | Trang học sinh — luyện đọc |
| `https://your-app.onrender.com/admin` | Trang Admin — quản lý bài |

### Workflow sử dụng:
1. **Admin** vào `/admin` → Click "RUN CRAWLER" → Duyệt bài hay
2. **Học sinh** vào `/` → Nhập tên → Chọn bài → Nhấn microphone → Đọc to
3. Kết quả hiện tức thì: WPM, Accuracy, Rank S/A/B/C

