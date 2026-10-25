#!/usr/bin/env sh
# Creates .devcontainer/.env with a random database password on first start.
# Runs on the host before the containers are created (initializeCommand).
set -eu
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  pw=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')
  printf 'POSTGRES_PASSWORD=%s\n' "$pw" > .env
  echo "Created .devcontainer/.env with a new database password."
fi
