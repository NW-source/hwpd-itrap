-- ===== HWPD i-Trap PostgreSQL Setup Script =====
-- Run as: sudo -u postgres psql -f /tmp/setup_itrap.sql

-- 1) Create user and database
CREATE USER itrap_admin WITH PASSWORD 'Hwpd@iTrap2026!Secure';
CREATE DATABASE itrap_db OWNER itrap_admin ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C' TEMPLATE template0;
GRANT ALL PRIVILEGES ON DATABASE itrap_db TO itrap_admin;
\c itrap_db

-- Allow itrap_admin to use and create in public schema
GRANT ALL ON SCHEMA public TO itrap_admin;

-- 2) Tables
CREATE TABLE IF NOT EXISTS cloud_daily_reports (
    report_date        DATE        PRIMARY KEY,
    priority_data      JSONB       NOT NULL DEFAULT '[]',
    dashboard_metrics  JSONB       NOT NULL DEFAULT '{}',
    uploaded_by        TEXT,
    record_count       INTEGER     DEFAULT 0,
    created_at         TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cloud_realtime (
    session_date       DATE        PRIMARY KEY,
    priority_json      JSONB       NOT NULL DEFAULT '[]',
    upload_count       INTEGER     DEFAULT 1,
    first_record_time  TEXT,
    last_record_time   TEXT,
    record_count       INTEGER     DEFAULT 0,
    uploaded_by        TEXT,
    updated_at         TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS historical_suspects (
    plate              TEXT        PRIMARY KEY,
    threat_type        TEXT,
    max_risk_score     INTEGER     DEFAULT 0,
    last_seen_date     TEXT,
    seen_count         INTEGER     DEFAULT 1,
    updated_at         TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS upload_log (
    id                 SERIAL      PRIMARY KEY,
    username           TEXT,
    display_name       TEXT,
    filename           TEXT,
    report_date        TEXT,
    record_count       INTEGER     DEFAULT 0,
    uploaded_at        TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS whitelist_master (
    plate              TEXT        PRIMARY KEY,
    note               TEXT,
    added_by           TEXT,
    added_at           TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_feedback (
    id                 SERIAL      PRIMARY KEY,
    target_id          TEXT,
    engine_type        TEXT,
    report_date        TEXT,
    is_correct         INTEGER     DEFAULT -1,
    notes              TEXT,
    user_id            TEXT,
    user_display       TEXT,
    feedback_date      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS target_status (
    target_id          TEXT        PRIMARY KEY,
    status             TEXT        DEFAULT '🔴 เฝ้าระวังใหม่',
    updated_by         TEXT,
    last_update        TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ip_blocklist (
    ip_address         TEXT        PRIMARY KEY,
    attempts           INTEGER     DEFAULT 0,
    blocked_until      TIMESTAMPTZ,
    last_attempt_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS system_users (
    username           TEXT        PRIMARY KEY,
    password_hash      TEXT        NOT NULL,
    display_name       TEXT,
    role               TEXT        DEFAULT 'viewer',
    is_active          BOOLEAN     DEFAULT TRUE,
    created_at         TIMESTAMPTZ DEFAULT now()
);

-- 3) Indexes for performance
CREATE INDEX IF NOT EXISTS idx_upload_log_date      ON upload_log(report_date);
CREATE INDEX IF NOT EXISTS idx_ai_feedback_target   ON ai_feedback(target_id);
CREATE INDEX IF NOT EXISTS idx_ai_feedback_date     ON ai_feedback(report_date);
CREATE INDEX IF NOT EXISTS idx_suspects_score       ON historical_suspects(max_risk_score DESC);
CREATE INDEX IF NOT EXISTS idx_target_status_id     ON target_status(target_id);

-- 5) LINE OA Configuration
CREATE TABLE IF NOT EXISTS line_config (
    id                      SERIAL      PRIMARY KEY,
    channel_access_token    TEXT        NOT NULL DEFAULT '',
    channel_secret          TEXT        NOT NULL DEFAULT '',
    webhook_url             TEXT        DEFAULT '',
    notify_watchlist_hit    BOOLEAN     DEFAULT TRUE,
    notify_daily_summary    BOOLEAN     DEFAULT TRUE,
    itrap_dashboard_url     TEXT        DEFAULT '',
    updated_at              TIMESTAMPTZ DEFAULT now()
);
-- Seed one empty row so the app can UPDATE instead of INSERT
INSERT INTO line_config (channel_access_token, channel_secret)
VALUES ('', '')
ON CONFLICT DO NOTHING;

-- 6) Watchlist (ทะเบียนที่ต้องเฝ้าระวัง — แยกจาก whitelist)
CREATE TABLE IF NOT EXISTS watchlist (
    plate           TEXT        PRIMARY KEY,
    reason          TEXT,
    risk_level      TEXT        DEFAULT 'HIGH',
    added_by        TEXT,
    added_at        TIMESTAMPTZ DEFAULT now(),
    is_active       BOOLEAN     DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_watchlist_active ON watchlist(is_active);

-- 4) Grant all tables to itrap_admin
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO itrap_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO itrap_admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO itrap_admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO itrap_admin;

\echo '===== itrap_db Schema Created Successfully ====='
