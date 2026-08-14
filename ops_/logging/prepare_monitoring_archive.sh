#!/usr/bin/env bash

# =============================================================================
# [START] Monitoring EC2 archive-directory preparation
# Purpose:
#   Idempotently create staging, final archive, and quarantine directories for
#   all six source EC2 roles before SSH/rsync delivery is enabled.
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

CONFIG_FILE="${CONFIG_FILE:-/etc/car-market/monitoring-log-archive.env}"
log_ops_load_config "$CONFIG_FILE"

: "${STAGING_ROOT:=/var/spool/car-market/incoming}"
: "${ARCHIVE_ROOT:=/var/log/car-market/archive}"
: "${QUARANTINE_ROOT:=/var/spool/car-market/quarantine}"
: "${STATE_DIR:=/var/lib/car-market/monitoring-log-archive}"
: "${STATUS_LOG:=/var/log/car-market/archive-ingest-status.jsonl}"
: "${LOCK_FILE:=/run/car-market/monitoring-log-archive.lock}"
: "${STAGING_OWNER:=logship}"
: "${STAGING_GROUP:=logship}"
: "${STAGING_ROOT_OWNER:=root}"
: "${STAGING_ROOT_GROUP:=logship}"
: "${ARCHIVE_OWNER:=root}"
: "${ARCHIVE_GROUP:=root}"
: "${OWNERSHIP_ENABLED:=1}"

for required_path in "$STAGING_ROOT" "$ARCHIVE_ROOT" "$QUARANTINE_ROOT" "$STATE_DIR" "$STATUS_LOG" "$LOCK_FILE"; do
    [[ "$required_path" == /* ]] || {
        printf 'Monitoring archive paths must be absolute: %s\n' "$required_path" >&2
        exit 2
    }
done
[[ "$OWNERSHIP_ENABLED" == "0" || "$OWNERSHIP_ENABLED" == "1" ]] || {
    printf 'OWNERSHIP_ENABLED must be 0 or 1\n' >&2
    exit 2
}

if [[ "$OWNERSHIP_ENABLED" == "0" ]]; then
    STAGING_OWNER=""
    STAGING_GROUP=""
    STAGING_ROOT_OWNER=""
    STAGING_ROOT_GROUP=""
    ARCHIVE_OWNER=""
    ARCHIVE_GROUP=""
fi

log_ops_create_directory "$STAGING_ROOT" 0750 "$STAGING_ROOT_OWNER" "$STAGING_ROOT_GROUP"
log_ops_create_directory "$ARCHIVE_ROOT" 0750 "$ARCHIVE_OWNER" "$ARCHIVE_GROUP"
log_ops_create_directory "$QUARANTINE_ROOT" 0750 "$ARCHIVE_OWNER" "$ARCHIVE_GROUP"
log_ops_create_directory "$STATE_DIR" 0750 "$ARCHIVE_OWNER" "$ARCHIVE_GROUP"
log_ops_create_directory "$(dirname -- "$STATUS_LOG")" 0750 "$ARCHIVE_OWNER" "$ARCHIVE_GROUP"
log_ops_create_directory "$(dirname -- "$LOCK_FILE")" 0750 "$ARCHIVE_OWNER" "$ARCHIVE_GROUP"

while IFS= read -r source_id; do
    log_ops_create_directory "${STAGING_ROOT}/${source_id}" 0750 "$STAGING_OWNER" "$STAGING_GROUP"
    log_ops_create_directory "${ARCHIVE_ROOT}/${source_id}" 0750 "$ARCHIVE_OWNER" "$ARCHIVE_GROUP"
    log_ops_create_directory "${QUARANTINE_ROOT}/${source_id}" 0750 "$ARCHIVE_OWNER" "$ARCHIVE_GROUP"
done < <(log_ops_source_ids)

# =============================================================================
# [END] Monitoring EC2 archive-directory preparation
# =============================================================================
