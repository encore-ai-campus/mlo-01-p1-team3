#!/usr/bin/env bash

# =============================================================================
# [START] Source EC2 hourly resource-log rotation launcher
# Purpose:
#   Run the dedicated logrotate configuration with its own state file while
#   sharing a lock with the daily shipper, so compression and transfer cannot
#   race with each other.
# =============================================================================

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LIB_FILE="${LOG_OPS_LIB_FILE:-${SCRIPT_DIR}/lib_log_ops.sh}"

[[ -r "$LIB_FILE" ]] || {
    printf 'Shared library is not readable: %s\n' "$LIB_FILE" >&2
    exit 1
}

# shellcheck source=lib_log_ops.sh
source "$LIB_FILE"

CONFIG_FILE="${CONFIG_FILE:-/etc/car-market/source-log-archive.env}"
log_ops_load_config "$CONFIG_FILE"

: "${SOURCE_ID:=}"
: "${LOCK_FILE:=/run/car-market/resource-log-archive.lock}"
: "${STATE_DIR:=/var/lib/car-market/resource-log-archive}"
: "${LOGROTATE_BIN:=/usr/sbin/logrotate}"
: "${LOGROTATE_CONFIG:=/etc/car-market/resource-logrotate.conf}"
: "${LOGROTATE_STATE:=/var/lib/car-market/resource-logrotate.status}"
: "${FLOCK_BIN:=/usr/bin/flock}"

log_ops_validate_source_id "$SOURCE_ID"
[[ "$LOCK_FILE" == /* ]] || { printf 'LOCK_FILE must be absolute\n' >&2; exit 2; }
[[ "$STATE_DIR" == /* ]] || { printf 'STATE_DIR must be absolute\n' >&2; exit 2; }
[[ "$LOGROTATE_CONFIG" == /* ]] || { printf 'LOGROTATE_CONFIG must be absolute\n' >&2; exit 2; }
[[ "$LOGROTATE_STATE" == /* ]] || { printf 'LOGROTATE_STATE must be absolute\n' >&2; exit 2; }
[[ -r "$LOGROTATE_CONFIG" ]] || { printf 'logrotate configuration is not readable: %s\n' "$LOGROTATE_CONFIG" >&2; exit 2; }

log_ops_require_executable "$LOGROTATE_BIN"
log_ops_require_executable "$FLOCK_BIN"
log_ops_create_directory "$(dirname -- "$LOCK_FILE")" 0750
log_ops_create_directory "$STATE_DIR" 0750
log_ops_create_directory "$(dirname -- "$LOGROTATE_STATE")" 0750

exec 9>"$LOCK_FILE"
if ! "$FLOCK_BIN" -n 9; then
    exit 0
fi

if "$LOGROTATE_BIN" --state "$LOGROTATE_STATE" "$LOGROTATE_CONFIG"; then
    log_ops_write_state "${STATE_DIR}/last_rotation_success" "$(log_ops_utc_now)"
    log_ops_write_state "${STATE_DIR}/last_rotation_error" ""
else
    exit_code=$?
    log_ops_write_state "${STATE_DIR}/last_rotation_error" "logrotate_failed:exit_${exit_code}"
    exit "$exit_code"
fi

# =============================================================================
# [END] Source EC2 hourly resource-log rotation launcher
# =============================================================================
