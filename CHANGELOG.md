# 📜 Changelog — AI English Speed Reader

Tài liệu này ghi lại toàn bộ thay đổi qua từng phiên bản của dự án.
Định dạng dựa theo [Keep a Changelog](https://keepachangelog.com/).

---

## [2.0.0] - 2026-08-18  ← **PHIÊN BẢN HIỆN TẠI**

### 🎨 Added — UI/UX hoàn toàn mới theo thiết kế UXpilot

**Trang học sinh (`/`) — Learning Room:**
- Sidebar navigation cố định (desktop) / drawer (mobile) với logo SpeedAI, profile avatar, menu items
- Hero dashboard: WPM Baseline lớn (420 WPM style), Word Retention Rate bar chart 7 ngày
- Reading pane: font Merriweather serif, highlight từ đọc đúng màu xanh lá mượt mà
- Microphone button tròn lớn 80px có hiệu ứng `pulse-ring` animation
- Audio Speed slider có waveform visualizer động
- Performance metrics panel: Reading Speed, Accuracy, Grade Rank (S/A/B/C)
- Article cards đẹp có ảnh thumbnail từ Unsplash, badge nguồn (BBC/CNN/Reuters), difficulty badge (Easy/Medium/Hard)
- Mobile bottom navigation (Home/Library/Stats/Admin)
- Local storage: lưu lịch sử điểm số, daily streak, weekly goal progress bar
- Section Library: xem toàn bộ bài báo dạng grid
- Section Metrics: lịch sử 10 buổi luyện gần nhất

**Trang admin (`/admin`) — Content Crawler Controller:**
- Dark sidebar `#1a252f` với active state màu xanh `brand-blue`
- Header có "Crawler Engine Online" badge animate pulse
- Source Configuration: dropdown chọn nguồn (BBC/CNN/Reuters), category, nút RUN CRAWLER
- Article queue: card bài báo có ảnh thumbnail grayscale → màu khi hover
- Approve/Reject từng bài, Select All, Batch Approve
- Mobile responsive: stacked layout + bottom tab bar

**Backend:**
- `estimate_difficulty()`: tự động phân loại Easy/Medium/Hard dựa trên độ dài từ
- `read_time()`: ước tính thời gian đọc (150 WPM)
- Ảnh thumbnail tự động gán theo độ khó bài báo

### Changed
- CSS hoàn toàn dùng Tailwind CDN + custom `tailwind.config`
- Font: Plus Jakarta Sans (UI) + Merriweather (reading text)
- Animation: `pulse-ring`, `wave`, `sidebar-drawer` slide transition

---

## [1.0.0] - 2026-08-14

### 🎉 Phát hành lần đầu

**Backend (Flask + Supabase + feedparser)**
- Khởi tạo ứng dụng Flask 1 file `app.py`, gom cả backend và frontend.
- Kết nối `supabase-py` để lưu bài báo đã duyệt (`articles`) và lịch sử
  điểm số học sinh (`scores`); tự động chuyển sang **chế độ demo** (dữ liệu
  mẫu, không lưu vĩnh viễn) nếu chưa cấu hình `SUPABASE_URL`/`SUPABASE_KEY`.
- Tích hợp `feedparser` quét tin từ 4 nguồn RSS quốc tế (BBC Technology,
  BBC World, CNN Top Stories, Reuters Business).
- API:
  - `POST /api/crawl` — quét RSS, trả danh sách bài chưa lưu.
  - `POST /api/approve` — Admin duyệt 1 bài, lưu vào Supabase.
  - `GET /api/articles` — lấy danh sách bài đã duyệt cho học sinh.
  - `POST /api/save_score` — lưu WPM / độ chính xác / xếp hạng.
- 2 route giao diện: `/` (khu vực học sinh) và `/admin` (khu vực quản lý).

**Frontend (nhúng HTML/CSS/JS trong Flask)**
- Thiết kế **Mobile-first**, responsive cho PC / iPhone / iPad / Android:
  - PC: card căn giữa, `max-width: 900px`.
  - Mobile: `padding: 15px`, không tràn viền, mọi nút bấm `min-height: 48px`.
- Font `Inter`, khung luyện đọc cỡ chữ 22px (mobile) → 26px (desktop),
  `line-height: 2` để đỡ mỏi mắt.
- Trang học sinh (`/`):
  - Ô nhập tên học sinh.
  - Danh sách bài báo dạng thẻ (chip) có thể chọn.
  - Nút "Bắt đầu đọc" kích hoạt Micro qua Web Speech API.
  - Khung đọc tự highlight từ đọc đúng (màu xanh lá, `transition: 0.3s`)
    và tự cuộn `scrollIntoView({behavior:'smooth', block:'center'})`.
  - Hộp kết quả hiển thị WPM, độ chính xác (%), xếp hạng S/A/B/C có đổ bóng.
- Trang Admin (`/admin`):
  - Nút "Quét tin mới" gọi `/api/crawl`.
  - Danh sách bài quét được, mỗi bài có nút "Duyệt" gọi `/api/approve`.

**Tài liệu**
- `README.md`: hướng dẫn cài đặt local, SQL tạo bảng Supabase, hướng dẫn
  deploy lên Render (Build/Start command, biến môi trường).
- `requirements.txt`: Flask, feedparser, supabase, gunicorn.

---

## [Chưa phát hành] - Đề xuất cho các bản sau

Ý tưởng cho các phiên bản tiếp theo (chưa triển khai):

- [ ] Trang xem lịch sử điểm số theo từng học sinh (biểu đồ tiến bộ theo thời gian).
- [ ] Cho Admin xoá / gỡ duyệt bài báo đã lưu.
- [ ] Hỗ trợ chọn giọng đọc mẫu (Text-to-Speech) trước khi luyện.
- [ ] Đăng nhập Admin bằng mật khẩu (hiện `/admin` đang mở công khai).
- [ ] Bộ lọc chủ đề bài báo (Công nghệ / Kinh tế / Môi trường...).

> Khi phát hành bản mới, hãy thêm mục `## [x.y.z] - YYYY-MM-DD` phía trên
> mục này, liệt kê các thay đổi theo nhóm: `Added` (thêm mới), `Changed`
> (thay đổi), `Fixed` (sửa lỗi), `Removed` (gỡ bỏ).
