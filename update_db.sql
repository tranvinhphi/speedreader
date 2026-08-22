ALTER TABLE articles ADD COLUMN IF NOT EXISTS published text default '';
ALTER TABLE articles ADD COLUMN IF NOT EXISTS lang text default 'en';
