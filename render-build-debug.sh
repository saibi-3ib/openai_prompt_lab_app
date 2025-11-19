#!/usr/bin/env bash
set -euo pipefail

# マスク表示関数
mask_url() {
  local url="$1"
  if [ -z "$url" ]; then
    echo "<NOT SET>"
    return
  fi
  # split userinfo@host/path
  local before_at="${url%@*}"
  local after_at="${url#*@}"
  if [ "$before_at" = "$url" ]; then
    # no @ present
    echo "${url:0:60}..."
    return
  fi
  local scheme="${before_at%%://*}"
  local userinfo="${before_at#*://}"
  local user="${userinfo%%:*}"
  # mask password if present
  if echo "$userinfo" | grep -q ':'; then
    echo "${scheme}://${user}:***@${after_at}"
  else
    echo "${scheme}://${userinfo}@${after_at}"
  fi
}

echo "==== build-time masked env (debug) ===="
# DATABASE_URL masked
echo -n "DATABASE_URL -> "
mask_url "${DATABASE_URL:-}"

# individual DB_* variables (password presence only shown as 'set'/'empty')
echo "DB_USER -> ${DB_USER:-<NOT SET>}"
if [ -n "${DB_PASSWORD:-}" ]; then echo "DB_PASSWORD -> set"; else echo "DB_PASSWORD -> <NOT SET>"; fi
echo "DB_NAME -> ${DB_NAME:-<NOT SET>}"
echo "DB_HOST -> ${DB_HOST:-<NOT SET>}"
echo "DB_PORT -> ${DB_PORT:-<NOT SET>}"

# optionally print entire env keys listing (masking values)
echo "==== Build-time keys matching DB_ or DATABASE_URL ===="
env | grep -i -E 'DB_|DATABASE_URL|POSTGRES|PG|PGHOST|PGPASSWORD|PGUSER' | sed -E 's/(=).*/=\*\*\*/' || true

# continue with the original build step by returning success (do not block build)
exit 0