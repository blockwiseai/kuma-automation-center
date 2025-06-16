#!/usr/bin/env sh
set -e

DB_PATH="/app/data/kuma.db"
# Use environment variable if set, otherwise use parameter, otherwise use default
if [ -n "$KUMA_PASS_HASH" ]; then
  PASSWORD_HASH="$KUMA_PASS_HASH"
else
  PASSWORD_HASH="${1:-\$2b\$10\$ixKQTXKjELdwVUGm8fzxxeF5E5m6oxkgxQ7Q/r60B7WR6Ycg5jMzS}"
fi

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

  # Insert the admin user with the provided hash
  sqlite3 "$DB_PATH" <<EOF
INSERT INTO "user" (
  "username",
  "password"
) VALUES (
  'admin',
  '$PASSWORD_HASH'
);
EOF

  echo "[init_admin] Admin user 'admin' created with provided password hash."
else
  echo "[init_admin] Detected $USER_COUNT existing user(s); skipping insert."
fi

exec node server/server.js