-- Thêm cột published vào articles nếu chưa có
ALTER TABLE articles ADD COLUMN IF NOT EXISTS published text default '';
