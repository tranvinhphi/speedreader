# 🎙️ AI English Speed Reader

Ứng dụng luyện đọc tiếng Anh tốc độ cao cho học sinh, dùng **Web Speech API**
để nhận diện giọng nói theo thời gian thực, tự động highlight từ đọc đúng
và chấm điểm (WPM / độ chính xác / xếp hạng S-A-B-C).

- Backend: Flask + `feedparser` (crawl RSS) + `supabase-py` (lưu trữ)
- Frontend: HTML/CSS/JS thuần (nhúng trong `app.py`), responsive Mobile-first
- Route `/` : khu vực học sinh · Route `/admin` : khu vực quản lý

> ⚠️ Web Speech API hiện chỉ hoạt động tốt nhất trên **Chrome** (desktop &
> Android). Safari/iOS hỗ trợ hạn chế — học sinh dùng iPhone/iPad nên mở
> bằng Chrome nếu có thể.

---

## 1. Cài đặt & chạy thử ở local

```bash
git clone <repo-cua-ban>
cd <repo-cua-ban>
python -m venv venv
source venv/bin/activate        # Windows: venv\\Scripts\\activate
pip install -r requirements.txt

# (Tùy chọn) cấu hình Supabase — nếu bỏ qua, app chạy ở "chế độ demo"
export SUPABASE_URL="https://xxxxxxxx.supabase.co"
export SUPABASE_KEY="eyJhbGciOi..."

python app.py
# Mở http://localhost:5000
```

---

## 2. Tạo bảng dữ liệu trên Supabase

Vào **Supabase Dashboard → SQL Editor**, chạy đoạn SQL sau:

```sql
-- Bảng lưu các bài báo đã được Admin duyệt
create table if not exists articles (
    id bigint generated always as identity primary key,
    title text not null,
    source text,
    url text,
    content text not null,
    created_at timestamptz default now()
);

-- Bảng lưu lịch sử điểm số của học sinh
create table if not exists scores (
    id bigint generated always as identity primary key,
    student_name text not null,
    article_title text,
    wpm integer default 0,
    accuracy integer default 0,
    rank text default 'C',
    created_at timestamptz default now()
);

-- (Khuyến nghị) Bật Row Level Security + policy cho phép đọc/ghi công khai
-- (chỉnh lại theo nhu cầu bảo mật thực tế của bạn)
alter table articles enable row level security;
alter table scores enable row level security;

create policy "public read articles" on articles for select using (true);
create policy "public insert articles" on articles for insert with check (true);
create policy "public read scores" on scores for select using (true);
create policy "public insert scores" on scores for insert with check (true);
```

Lấy `SUPABASE_URL` và `SUPABASE_KEY` (dùng **anon/public key** hoặc
**service_role key** nếu chạy hoàn toàn phía server) tại
**Project Settings → API**.

---

## 3. Deploy lên Render

1. Đẩy code lên GitHub (đã có sẵn `app.py`, `requirements.txt`, `README.md`).
2. Vào [render.com](https://render.com) → **New → Web Service** → kết nối
   repo GitHub.
3. Cấu hình:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
4. Vào tab **Environment**, thêm 2 biến:
   - `SUPABASE_URL` = URL project Supabase của bạn
   - `SUPABASE_KEY` = API key Supabase của bạn
5. Bấm **Deploy**. Sau khi build xong, Render sẽ cấp cho bạn 1 URL dạng
   `https://ten-app.onrender.com`.
   - Trang học sinh: `https://ten-app.onrender.com/`
   - Trang admin: `https://ten-app.onrender.com/admin`

---

## 4. Cấu trúc chức năng

| Route              | Mô tả                                                        |
|---------------------|---------------------------------------------------------------|
| `GET /`             | Trang học sinh: chọn bài, bắt đầu đọc, xem kết quả            |
| `GET /admin`        | Trang quản trị: quét tin RSS, duyệt bài                       |
| `POST /api/crawl`   | Quét RSS (BBC/CNN/Reuters), trả JSON danh sách bài chưa lưu   |
| `POST /api/approve` | Lưu 1 bài báo đã duyệt vào bảng `articles` trên Supabase      |
| `GET /api/articles` | Lấy danh sách bài đã duyệt cho học sinh chọn                  |
| `POST /api/save_score` | Lưu kết quả luyện đọc (WPM/độ chính xác/rank) vào `scores` |

## 5. Ghi chú kỹ thuật

- Nếu chưa cấu hình `SUPABASE_URL`/`SUPABASE_KEY`, ứng dụng tự động chuyển
  sang **chế độ demo**: trang học sinh vẫn hiển thị 3 bài đọc mẫu để bạn
  kiểm thử giao diện và tính năng nhận diện giọng nói ngay lập tức.
- Nguồn RSS có thể chỉnh sửa trong biến `RSS_FEEDS` ở đầu `app.py`.
- Công thức xếp hạng (có thể điều chỉnh trong hàm `calcRank`):

  | Rank | Điều kiện                          |
  |------|-------------------------------------|
  | S    | Độ chính xác ≥ 95% và WPM ≥ 130      |
  | A    | Độ chính xác ≥ 90% và WPM ≥ 100      |
  | B    | Độ chính xác ≥ 80% và WPM ≥ 70       |
  | C    | Còn lại                              |
