-- =========================================================
-- สร้าง Table ip_blocklist สำหรับ Brute-Force Protection
-- รัน SQL นี้ใน Supabase → SQL Editor
-- =========================================================

CREATE TABLE IF NOT EXISTS ip_blocklist (
    ip_address    TEXT        PRIMARY KEY,
    attempt_count INTEGER     NOT NULL DEFAULT 0,
    first_attempt TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_attempt  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    blocked_until TIMESTAMPTZ          DEFAULT NULL
);

-- Index สำหรับ query ที่เร็ว
CREATE INDEX IF NOT EXISTS idx_ip_blocked_until ON ip_blocklist (blocked_until);

-- Row Level Security (ให้ service_role เข้าถึงได้)
ALTER TABLE ip_blocklist ENABLE ROW LEVEL SECURITY;

-- Policy: service_role full access
CREATE POLICY "service_role_all" ON ip_blocklist
    FOR ALL USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- Auto-cleanup: ลบ records เก่ากว่า 7 วัน (optional scheduled job)
-- DELETE FROM ip_blocklist WHERE last_attempt < NOW() - INTERVAL '7 days';
