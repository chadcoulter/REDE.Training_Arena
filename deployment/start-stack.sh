#!/bin/sh
set -eu

cleanup() {
  status=$?
  trap - INT TERM EXIT
  if [ -n "${ADAPTER_PID:-}" ] && kill -0 "$ADAPTER_PID" 2>/dev/null; then
    kill "$ADAPTER_PID" 2>/dev/null || true
  fi
  if [ -n "${EVENNIA_PID:-}" ] && kill -0 "$EVENNIA_PID" 2>/dev/null; then
    kill "$EVENNIA_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
  exit "$status"
}

trap cleanup INT TERM EXIT

cd /app

echo "[arena-stack] applying Evennia database migrations"
evennia migrate

echo "[arena-stack] starting MCP adapter on ${PORT:-8787}"
node /app/adapter/server.js &
ADAPTER_PID=$!

echo "[arena-stack] starting Evennia (telnet 4000, web 4001)"
evennia start --log &
EVENNIA_PID=$!

# Cloudflare requires all declared ports to remain live. If either process dies,
# terminate the stack so the platform can restart a clean container instance.
while kill -0 "$ADAPTER_PID" 2>/dev/null && kill -0 "$EVENNIA_PID" 2>/dev/null; do
  sleep 2
done

echo "[arena-stack] a required process exited; terminating container" >&2
exit 1
