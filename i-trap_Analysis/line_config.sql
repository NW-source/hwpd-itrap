-- ?????????? line_config ???????????
CREATE TABLE IF NOT EXISTS line_config (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ?????????? watchlist ???????????
CREATE TABLE IF NOT EXISTS watchlist (
    id SERIAL PRIMARY KEY,
    plate VARCHAR(20) NOT NULL,
    reason TEXT,
    risk_score INT DEFAULT 0,
    added_by VARCHAR(100) DEFAULT 'system',
    added_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

GRANT ALL ON line_config TO itrap_admin;
GRANT ALL ON watchlist TO itrap_admin;

-- ??? LINE credentials
INSERT INTO line_config (key, value) VALUES ('channel_secret', '96a5e5f543af67e2af838d7296585308')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();

INSERT INTO line_config (key, value) VALUES ('channel_token', '7EwiDl3iORhmwEaGvPT3rWjuohuuV6sRZbIxHPHKPwOabX5Z4L0221bZSGVprgJOE7gCAQ8oumoR1XbMRwPLGgzDXVMc2EKawNCJYmUzNm3dWss/PA8VXnVdoLRUk485LsXWELIyLZqW+BddA5mb9wdB04t89/1O/w1cDnyilFU=')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();

SELECT key, LEFT(value,20) AS preview, updated_at FROM line_config;