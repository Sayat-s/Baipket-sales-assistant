#!/usr/bin/env bash
# Перезапускает listener.py, если он упал.
cd "$(dirname "${BASH_SOURCE[0]}")"
mkdir -p tmp
while true; do
  rm -f tmp/listener.pid
  python3 -I listener.py >> tmp/listener.log 2>&1
  sleep 3
done
