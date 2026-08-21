-- ============================================================
-- AI SPEED READER v3.0.0 — Supabase Database Setup
-- Chạy toàn bộ script này trong Supabase → SQL Editor
-- Dùng IF NOT EXISTS và DROP POLICY IF EXISTS để tránh lỗi
-- ============================================================

-- ── 1. Bảng bài báo đã duyệt ─────────────────────────────
CREATE TABLE IF NOT EXISTS articles (
    id          bigint generated always as identity primary key,
    title       text not null,
    source      text,
    url         text,
    content     text not null,
    difficulty  text default 'Medium',
    image       text,
    read_time   text,
    created_at  timestamptz default now()
);

-- ── 2. Bảng học viên (TÀI KHOẢN) ────────────────────────
CREATE TABLE IF NOT EXISTS students (
    id             bigint generated always as identity primary key,
    name           text not null unique,
    password_hash  text not null,
    streak         integer default 0,
    total_sessions integer default 0,
    created_at     timestamptz default now()
);

-- ── 3. Bảng điểm số (liên kết với học viên) ─────────────
CREATE TABLE IF NOT EXISTS scores (
    id            bigint generated always as identity primary key,
    student_id    bigint references students(id) on delete cascade,
    student_name  text not null,
    article_title text,
    article_id    text,
    wpm           integer default 0,
    accuracy      integer default 0,
    rank          text default 'C',
    words_read    integer default 0,
    created_at    timestamptz default now()
);

-- Index để query nhanh
CREATE INDEX IF NOT EXISTS idx_scores_student_id ON scores(student_id);
CREATE INDEX IF NOT EXISTS idx_scores_created_at ON scores(created_at desc);
CREATE INDEX IF NOT EXISTS idx_articles_created_at ON articles(created_at desc);

-- ── 4. Row Level Security ─────────────────────────────────
ALTER TABLE articles ENABLE ROW LEVEL SECURITY;
ALTER TABLE students ENABLE ROW LEVEL SECURITY;
ALTER TABLE scores   ENABLE ROW LEVEL SECURITY;

-- Xoá policies cũ nếu tồn tại (tránh lỗi 42710)
DROP POLICY IF EXISTS "public read articles"  ON articles;
DROP POLICY IF EXISTS "public insert articles" ON articles;
DROP POLICY IF EXISTS "public delete articles" ON articles;
DROP POLICY IF EXISTS "public read students"  ON students;
DROP POLICY IF EXISTS "public insert students" ON students;
DROP POLICY IF EXISTS "public read scores"    ON scores;
DROP POLICY IF EXISTS "public insert scores"  ON scores;

-- Tạo lại policies
CREATE POLICY "public read articles"   ON articles FOR SELECT USING (true);
CREATE POLICY "public insert articles" ON articles FOR INSERT WITH CHECK (true);
CREATE POLICY "public delete articles" ON articles FOR DELETE USING (true);

CREATE POLICY "public read students"   ON students FOR SELECT USING (true);
CREATE POLICY "public insert students" ON students FOR INSERT WITH CHECK (true);
CREATE POLICY "public update students" ON students FOR UPDATE USING (true);

CREATE POLICY "public read scores"     ON scores FOR SELECT USING (true);
CREATE POLICY "public insert scores"   ON scores FOR INSERT WITH CHECK (true);

-- ── 5. Kiểm tra (chạy sau khi setup xong) ────────────────
-- SELECT table_name FROM information_schema.tables
-- WHERE table_schema = 'public'
-- ORDER BY table_name;
