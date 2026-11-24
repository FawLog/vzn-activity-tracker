#!/usr/bin/env sh
set -eu

project_directory=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_directory"
docker compose exec -T backend python -m app.backup create
