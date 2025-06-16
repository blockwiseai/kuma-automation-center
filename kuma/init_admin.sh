#!/usr/bin/env sh
set -e

DB_PATH="/app/data/kuma.db"
# Use environment variable if set, otherwise use parameter, otherwise use default
ADMIN_PASSWORD="${KUMA_PASS:-${1:-counter123}}"

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
  echo "[init_admin] No users found; creating initial admin…"

  # Generate bcrypt hash for the provided password
  HASHED_PASSWORD=$(node -e "
    const bcrypt = require('bcryptjs');
    const password = process.argv[1];
    const hash = bcrypt.hashSync(password, 10);
    console.log(hash);
  " "$ADMIN_PASSWORD")

  # Insert the admin user with the hashed password
  sqlite3 "$DB_PATH" <<EOF
INSERT INTO "user" (
  "username",
  "password"
) VALUES (
  'admin',
  '$HASHED_PASSWORD'
);
EOF

  echo "[init_admin] Admin user 'admin' created."
else
  echo "[init_admin] Detected $USER_COUNT existing user(s); skipping insert."
fi

exec node server/server.js