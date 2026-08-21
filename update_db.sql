-- Chạy trong Supabase SQL Editor để thêm cột mới
ALTER TABLE articles ADD COLUMN IF NOT EXISTS published text default '';
ALTER TABLE articles ADD COLUMN IF NOT EXISTS lang text default 'en';
