CREATE INDEX idx_sessions_auth_created
  ON admin_sessions(is_authenticated, created_at DESC);

CREATE INDEX idx_login_attempts_window
  ON login_attempts(window_started_at);
