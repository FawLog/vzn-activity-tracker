#!/bin/bash
# Shared, root-owned health-check helpers for the VZN deployment scripts.

vzn_health_response_is_ready() {
  python3 -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    raise SystemExit(1)

raise SystemExit(
    0
    if payload.get("status") == "ok"
    and payload.get("database") == "ready"
    and isinstance(payload.get("migration_version"), int)
    else 1
)
'
}

wait_for_public_https_health() {
  local domain="$1"
  local public_ipv4="$2"
  local max_attempts="$3"
  local connect_timeout_seconds="$4"
  local request_timeout_seconds="$5"
  local retry_delay_seconds="$6"
  local attempt response

  [[ "${max_attempts}" =~ ^[1-9][0-9]*$ ]] || return 2
  [[ "${connect_timeout_seconds}" =~ ^[1-9][0-9]*$ ]] || return 2
  [[ "${request_timeout_seconds}" =~ ^[1-9][0-9]*$ ]] || return 2
  [[ "${retry_delay_seconds}" =~ ^[0-9]+$ ]] || return 2

  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    if response="$(curl --fail --silent --show-error \
      --connect-timeout "${connect_timeout_seconds}" \
      --max-time "${request_timeout_seconds}" \
      --resolve "${domain}:443:${public_ipv4}" \
      "https://${domain}/api/v1/health")" \
      && printf '%s' "${response}" | vzn_health_response_is_ready; then
      printf 'Public HTTPS health check succeeded on attempt %s/%s.\n' \
        "${attempt}" "${max_attempts}"
      return 0
    fi

    if (( attempt < max_attempts )); then
      printf 'Public HTTPS health check attempt %s/%s failed; retrying in %ss.\n' \
        "${attempt}" "${max_attempts}" "${retry_delay_seconds}" >&2
      sleep "${retry_delay_seconds}"
    fi
  done

  printf 'Public HTTPS health check failed after %s attempts. The VZN rollback will run.\n' \
    "${max_attempts}" >&2
  return 1
}
