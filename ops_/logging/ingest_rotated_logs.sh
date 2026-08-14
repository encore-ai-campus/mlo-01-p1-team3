#!/usr/bin/env bash

# =============================================================================
# [START] Monitoring EC2 daily rotated-log ingest
# Purpose:
#   Validate gzip archives delivered by all six source EC2s and move each file
#   into its source-specific final directory. Corrupt or conflicting files are
#   quarantined and never overwrite an existing archive.
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
: "${FLOCK_BIN:=/usr/bin/flock}"
: "${GZIP_BIN:=/usr/bin/gzip}"
: "${ARCHIVE_OWNER:=root}"
: "${ARCHIVE_GROUP:=root}"
: "${ARCHIVE_FILE_MODE:=0640}"
: "${OWNERSHIP_ENABLED:=1}"

LAST_SUCCESS_FILE="${STATE_DIR}/last_ingest_success"
LAST_ERROR_FILE="${STATE_DIR}/last_ingest_error"
LAST_SUCCESS=""
LAST_ERROR=""
RESULT="idle"
LOCK_ACQUIRED=0
HAD_PARTIAL=0


fail() {
    LAST_ERROR="$1"
    RESULT="failed"
    printf 'ERROR: %s\n' "$LAST_ERROR" >&2
    return 1
}


monitoring_pending_count() {
    local source_id
    local count=0
    local source_count

    while IFS= read -r source_id; do
        source_count="$(log_ops_pending_count "${STAGING_ROOT}/${source_id}" "${source_id}-resource.log-*.gz")"
        ((count += source_count))
    done < <(log_ops_source_ids)
    printf '%s' "$count"
}


monitoring_oldest_pending() {
    local source_id
    local source_oldest
    local source_epoch
    local oldest_epoch=""

    while IFS= read -r source_id; do
        source_oldest="$(log_ops_oldest_pending "${STAGING_ROOT}/${source_id}" "${source_id}-resource.log-*.gz")"
        [[ -n "$source_oldest" ]] || continue
        source_epoch="$(date -u -d "$source_oldest" +%s)"
        if [[ -z "$oldest_epoch" || "$source_epoch" -lt "$oldest_epoch" ]]; then
            oldest_epoch="$source_epoch"
        fi
    done < <(log_ops_source_ids)

    if [[ -n "$oldest_epoch" ]]; then
        date -u -d "@${oldest_epoch}" +"%Y-%m-%dT%H:%M:%SZ"
    fi
}


emit_status() {
    local exit_code=$?
    local pending_count
    local oldest_pending

    ((LOCK_ACQUIRED == 1)) || return "$exit_code"

    if ((exit_code != 0)); then
        RESULT="failed"
        [[ -n "$LAST_ERROR" ]] || LAST_ERROR="script_failed:exit_${exit_code}"
    fi

    pending_count="$(monitoring_pending_count || printf '0')"
    oldest_pending="$(monitoring_oldest_pending || true)"
    if [[ "$RESULT" == "idle" && "$pending_count" -gt 0 ]]; then
        RESULT="pending"
    fi

    log_ops_write_state "$LAST_SUCCESS_FILE" "$LAST_SUCCESS" || true
    log_ops_write_state "$LAST_ERROR_FILE" "$LAST_ERROR" || true
    log_ops_write_status_record \
        "$STATUS_LOG" \
        "monitoring_resource_log_ingest" \
        "all" \
        "$RESULT" \
        "$pending_count" \
        "$oldest_pending" \
        "$LAST_SUCCESS" \
        "$LAST_ERROR" || true

    return "$exit_code"
}


quarantine_file() {
    local source_id="$1"
    local archive_path="$2"
    local reason="$3"
    local archive_name
    local destination

    archive_name="$(basename -- "$archive_path")"
    destination="${QUARANTINE_ROOT}/${source_id}/${archive_name}.${reason}-$(date -u +"%Y%m%dT%H%M%SZ")"
    mv -- "$archive_path" "$destination"
    LAST_ERROR="${reason}:${source_id}:${archive_name}"
    RESULT="partial"
    HAD_PARTIAL=1
}


apply_archive_permissions() {
    local archive_path="$1"

    chmod "$ARCHIVE_FILE_MODE" "$archive_path"
    if [[ "$OWNERSHIP_ENABLED" == "1" ]]; then
        chown "${ARCHIVE_OWNER}:${ARCHIVE_GROUP}" "$archive_path"
    fi
}


validate_configuration() {
    local required_path
    local source_id

    for required_path in "$STAGING_ROOT" "$ARCHIVE_ROOT" "$QUARANTINE_ROOT" "$STATE_DIR" "$STATUS_LOG" "$LOCK_FILE"; do
        [[ "$required_path" == /* ]] || fail "monitoring_path_must_be_absolute:${required_path}"
    done
    [[ "$ARCHIVE_FILE_MODE" =~ ^0?[0-7]{3,4}$ ]] || fail "archive_file_mode_must_be_octal"
    [[ "$OWNERSHIP_ENABLED" == "0" || "$OWNERSHIP_ENABLED" == "1" ]] || fail "ownership_enabled_must_be_0_or_1"
    log_ops_require_executable "$FLOCK_BIN"
    log_ops_require_executable "$GZIP_BIN"

    while IFS= read -r source_id; do
        log_ops_same_filesystem "${STAGING_ROOT}/${source_id}" "${ARCHIVE_ROOT}/${source_id}" || {
            fail "staging_and_archive_must_share_filesystem:${source_id}"
        }
    done < <(log_ops_source_ids)
}


CONFIG_FILE="$CONFIG_FILE" LOG_OPS_LIB_FILE="$LIB_FILE" "$BASH" "${SCRIPT_DIR}/prepare_monitoring_archive.sh"

LAST_SUCCESS="$(log_ops_read_state "$LAST_SUCCESS_FILE")"
LAST_ERROR="$(log_ops_read_state "$LAST_ERROR_FILE")"

exec 9>"$LOCK_FILE"
if ! "$FLOCK_BIN" -n 9; then
    exit 0
fi
LOCK_ACQUIRED=1
trap emit_status EXIT

validate_configuration

while IFS= read -r source_id; do
    shopt -s nullglob
    archives=("${STAGING_ROOT}/${source_id}"/"${source_id}"-resource.log-*.gz)
    shopt -u nullglob

    for archive_path in "${archives[@]}"; do
        [[ -e "$archive_path" || -L "$archive_path" ]] || continue
        archive_name="$(basename -- "$archive_path")"
        expected_pattern="^${source_id}-resource\\.log-[0-9]{8}T[0-9]{6}\\.gz$"
        [[ "$archive_name" =~ $expected_pattern ]] || {
            quarantine_file "$source_id" "$archive_path" "unexpected_name"
            continue
        }

        if [[ -L "$archive_path" || ! -f "$archive_path" ]]; then
            quarantine_file "$source_id" "$archive_path" "unexpected_type"
            continue
        fi

        if [[ "$(stat -c '%h' -- "$archive_path")" != "1" ]]; then
            quarantine_file "$source_id" "$archive_path" "multiple_hardlinks"
            continue
        fi

        if ! "$GZIP_BIN" -t -- "$archive_path"; then
            quarantine_file "$source_id" "$archive_path" "invalid_gzip"
            continue
        fi

        destination="${ARCHIVE_ROOT}/${source_id}/${archive_name}"
        if [[ -e "$destination" ]]; then
            if cmp -s -- "$archive_path" "$destination"; then
                rm -f -- "$archive_path"
                LAST_SUCCESS="$(log_ops_utc_now)"
                LAST_ERROR=""
                if ((HAD_PARTIAL == 0)); then
                    RESULT="success"
                fi
            else
                quarantine_file "$source_id" "$archive_path" "name_conflict"
            fi
            continue
        fi

        apply_archive_permissions "$archive_path"
        mv -- "$archive_path" "$destination"
        LAST_SUCCESS="$(log_ops_utc_now)"
        LAST_ERROR=""
        if ((HAD_PARTIAL == 0)); then
            RESULT="success"
        fi
    done
done < <(log_ops_source_ids)

# =============================================================================
# [END] Monitoring EC2 daily rotated-log ingest
# =============================================================================
