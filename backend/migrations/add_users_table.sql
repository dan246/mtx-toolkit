-- Authentication: users table
-- Run this on existing deployments before restarting containers.
-- New deployments get this table automatically via db.create_all().
--
-- After applying, a bootstrap admin is created on first app startup using
-- BOOTSTRAP_ADMIN_USERNAME / BOOTSTRAP_ADMIN_PASSWORD (default admin/admin).
-- Change that password immediately via POST /api/auth/change-password.

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(50)  DEFAULT 'admin',
    is_active     BOOLEAN      DEFAULT TRUE,
    last_login    TIMESTAMP,
    created_at    TIMESTAMP    DEFAULT NOW(),
    updated_at    TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_users_username ON users (username);
