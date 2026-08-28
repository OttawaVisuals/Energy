CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  page_slug TEXT NOT NULL,
  rating TEXT NOT NULL CHECK (rating IN ('clear', 'almost', 'not-yet')),
  comment TEXT NOT NULL DEFAULT '',
  context_json TEXT NOT NULL DEFAULT '[]',
  submitted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  dedupe_key TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS feedback_page_submitted
  ON feedback (page_slug, submitted_at DESC);

CREATE INDEX IF NOT EXISTS feedback_submitted
  ON feedback (submitted_at DESC);
