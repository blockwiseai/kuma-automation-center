#!/usr/bin/env sh
set -e

DB_PATH="/app/data/kuma.db"
# Use environment variable if set, otherwise use parameter, otherwise use default
ADMIN_PASSWORD="${KUMA_PASS:-${1:-counter123}}"
# Webhook URL pointing to miner-restarter service
WEBHOOK_URL="${WEBHOOK_URL:-http://miner-restarter:9999/webhook}"

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
fi

# Check if we need to create default webhook notification
NOTIFICATION_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM notification WHERE name = 'Docker Network Webhook';" 2>/dev/null || echo "0")

if [ "$NOTIFICATION_COUNT" -eq 0 ]; then
  echo "[init_admin] Creating default webhook notification..."
  
  # Create the notification using SQLite
  sqlite3 "$DB_PATH" <<EOF
INSERT INTO "notification" (
  "name",
  "type",
  "isDefault",
  "active",
  "userId",
  "config"
) VALUES (
  'miner-restarter webhook',
  'webhook',
  1,
  1,
  1,
  json_object(
    'webhookURL', '$WEBHOOK_URL',
    'webhookContentType', 'application/json',
    'webhookMethod', 'POST'
  )
);
EOF

  echo "[init_admin] Default webhook notification created (URL: $WEBHOOK_URL)"
  
  # Since this is set as default (isDefault=1), it will automatically apply to all new monitors
  # For existing monitors, we need to link them to this notification
  
  NOTIFICATION_ID=$(sqlite3 "$DB_PATH" "SELECT id FROM notification WHERE name = 'miner-restarter webhook' LIMIT 1;" 2>/dev/null || echo "")
  
  if [ -n "$NOTIFICATION_ID" ]; then
    echo "[init_admin] Applying webhook notification to all existing monitors..."
    
    # Get all monitor IDs that don't have this notification
    sqlite3 "$DB_PATH" <<EOF
INSERT INTO monitor_notification (monitorId, notificationId)
SELECT m.id, $NOTIFICATION_ID
FROM monitor m
WHERE m.type != 'group' 
  AND NOT EXISTS (
    SELECT 1 FROM monitor_notification mn 
    WHERE mn.monitorId = m.id AND mn.notificationId = $NOTIFICATION_ID
  );
EOF
    
    echo "[init_admin] Webhook notification applied to all monitors."
  fi
else
  echo "[init_admin] Webhook notification already exists; skipping."
fi

exec node server/server.js