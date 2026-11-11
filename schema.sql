PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS accounts (
    handle TEXT PRIMARY KEY,
    display_name TEXT,
    platform TEXT NOT NULL CHECK (platform = 'x'),
    confirmed_by_user INTEGER NOT NULL DEFAULT 0 CHECK (confirmed_by_user IN (0, 1)),
    browser_separate_designated INTEGER NOT NULL DEFAULT 0 CHECK (browser_separate_designated IN (0, 1)),
    confirmed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workflow_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY,
    x_url TEXT NOT NULL UNIQUE,
    status_id TEXT,
    account_handle TEXT NOT NULL,
    body_text TEXT,
    language TEXT,
    project_short TEXT,
    read_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (read_status IN ('pending', 'read', 'unavailable')),
    read_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_handle) REFERENCES accounts(handle)
);

CREATE TABLE IF NOT EXISTS reply_drafts (
    id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL,
    option_no INTEGER NOT NULL CHECK (option_no BETWEEN 1 AND 3),
    text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    reply_probability INTEGER CHECK (reply_probability BETWEEN 0 AND 100),
    stars INTEGER CHECK (stars BETWEEN 1 AND 5),
    recommended INTEGER NOT NULL DEFAULT 0 CHECK (recommended IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'recommended', 'posted', 'not_used', 'rejected')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id),
    UNIQUE (post_id, option_no)
);

CREATE TABLE IF NOT EXISTS posted_replies (
    id INTEGER PRIMARY KEY,
    account_handle TEXT NOT NULL,
    post_id INTEGER,
    draft_id INTEGER,
    text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('user_confirmed', 'imported')),
    posted_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_handle) REFERENCES accounts(handle),
    FOREIGN KEY (post_id) REFERENCES posts(id),
    FOREIGN KEY (draft_id) REFERENCES reply_drafts(id),
    UNIQUE (account_handle, normalized_text)
);

CREATE TABLE IF NOT EXISTS engagement_status (
    post_id INTEGER PRIMARY KEY,
    reply_manual_status TEXT NOT NULL DEFAULT 'not_confirmed'
        CHECK (reply_manual_status IN ('not_confirmed', 'user_posted', 'not_posted', 'unknown')),
    like_manual_status TEXT NOT NULL DEFAULT 'not_confirmed'
        CHECK (like_manual_status IN ('not_confirmed', 'user_liked', 'not_liked', 'unknown')),
    verification_note TEXT,
    verified_at TEXT,
    FOREIGN KEY (post_id) REFERENCES posts(id)
);

CREATE TABLE IF NOT EXISTS workflow_events (
    id INTEGER PRIMARY KEY,
    event_type TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reply_drafts_normalized
    ON reply_drafts(normalized_text);
CREATE INDEX IF NOT EXISTS idx_posted_replies_account
    ON posted_replies(account_handle, normalized_text);
