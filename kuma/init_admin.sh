#!/usr/bin/env sh
set -e

DB_PATH="/app/data/kuma.db"

if [ ! -f "$DB_PATH" ]; then
  echo "[init_admin] No database found; starting Kuma to initialize schema…"
  node server/server.js &
  KUMA_PID=$!

  while [ ! -f "$DB_PATH" ]; do
    sleep 1
  done

  sleep 3

  # Stop the temporary instance
  kill $KUMA_PID
  wait $KUMA_PID 2>/dev/null || true
fi

USER_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM user;" 2>/dev/null || echo "0")
if [ "$USER_COUNT" -eq 0 ]; then
  echo "[init_admin] No users found; inserting initial admin…"

  # The bcrypt hash for “counter123” (salt rounds = 10)
  SQLITE_HASH='$2b$10$ixKQTXKjELdwVUGm8fzxxeF5E5m6oxkgxQ7Q/r60B7WR6Ycg5jMzS'

  sqlite3 "$DB_PATH" <<'EOF'
INSERT INTO "user" (
  "username",
  "password"
) VALUES (
  'admin',
  '$2b$10$ixKQTXKjELdwVUGm8fzxxeF5E5m6oxkgxQ7Q/r60B7WR6Ycg5jMzS'
);
EOF

  echo "[init_admin] Admin user 'admin' created (password = counter123)."
else
  echo "[init_admin] Detected $USER_COUNT existing user(s); skipping insert."
fi

exec node server/server.js
