#!/usr/bin/env bash

# =============================================================================
# [START] Source EC2 daily rotated-log shipper
# Purpose:
#   Send completed hourly resource.log gzip files to the source-specific
#   Monitoring staging directory with rsync over SSH. Successfully delivered
#   files are removed locally; failures remain for the next daily retry.
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
: "${ROTATED_DIR:=/var/log/car-market/archive-outbox}"
: "${ROTATED_GLOB:=resource.log-*.gz}"
: "${LOCK_FILE:=/run/car-market/resource-log-archive.lock}"
: "${STATE_DIR:=/var/lib/car-market/resource-log-archive}"
: "${STATUS_LOG:=/var/log/car-market/archive-status.jsonl}"
: "${RSYNC_BIN:=/usr/bin/rsync}"
: "${SSH_BIN:=/usr/bin/ssh}"
: "${FLOCK_BIN:=/usr/bin/flock}"
: "${RSYNC_TIMEOUT_SECONDS:=120}"
: "${SSH_PORT:=22}"
: "${SSH_KEY:=}"
: "${KNOWN_HOSTS:=}"
: "${REMOTE_USER:=}"
: "${MONITORING_HOST:=}"
: "${REMOTE_STAGING_ROOT:=/var/spool/car-market/incoming}"

LAST_SUCCESS_FILE="${STATE_DIR}/last_ship_success"
LAST_ERROR_FILE="${STATE_DIR}/last_ship_error"
LAST_SUCCESS=""
LAST_ERROR=""
RESULT="idle"
LOCK_ACQUIRED=0


fail() {
    LAST_ERROR="$1"
    RESULT="failed"
    printf 'ERROR: %s\n' "$LAST_ERROR" >&2
    return 1
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

    pending_count="$(log_ops_pending_count "$ROTATED_DIR" "$ROTATED_GLOB" || printf '0')"
    oldest_pending="$(log_ops_oldest_pending "$ROTATED_DIR" "$ROTATED_GLOB" || true)"
    if [[ "$RESULT" == "idle" && "$pending_count" -gt 0 ]]; then
        RESULT="pending"
    fi

    log_ops_write_state "$LAST_SUCCESS_FILE" "$LAST_SUCCESS" || true
    log_ops_write_state "$LAST_ERROR_FILE" "$LAST_ERROR" || true
    log_ops_write_status_record \
        "$STATUS_LOG" \
        "source_resource_log_shipper" \
        "$SOURCE_ID" \
        "$RESULT" \
        "$pending_count" \
        "$oldest_pending" \
        "$LAST_SUCCESS" \
        "$LAST_ERROR" || true

    return "$exit_code"
}


validate_configuration() {
    log_ops_validate_source_id "$SOURCE_ID"
    [[ "$ROTATED_DIR" == /* ]] || fail "rotated_dir_must_be_absolute"
    [[ "$REMOTE_STAGING_ROOT" == /* ]] || fail "remote_staging_root_must_be_absolute"
    log_ops_validate_managed_directory "$ROTATED_DIR" || fail "rotated_dir_is_not_safe"
    log_ops_validate_managed_directory "$REMOTE_STAGING_ROOT" || fail "remote_staging_root_is_not_safe"
    [[ "$ROTATED_GLOB" == "resource.log-*.gz" ]] || fail "rotated_glob_must_be_resource_log_gzip"
    [[ "$RSYNC_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] || fail "rsync_timeout_must_be_positive_integer"
    [[ "$SSH_PORT" =~ ^[1-9][0-9]*$ ]] || fail "ssh_port_must_be_positive_integer"
    [[ -n "$REMOTE_USER" ]] || fail "remote_user_is_required"
    [[ -n "$MONITORING_HOST" ]] || fail "monitoring_host_is_required"
    [[ -r "$SSH_KEY" ]] || fail "ssh_key_is_not_readable:${SSH_KEY}"
    [[ -r "$KNOWN_HOSTS" ]] || fail "known_hosts_is_not_readable:${KNOWN_HOSTS}"
    log_ops_require_executable "$RSYNC_BIN"
    log_ops_require_executable "$SSH_BIN"
    log_ops_require_executable "$FLOCK_BIN"
}


build_rsync_ssh_command() {
    local command_parts=(
        "$SSH_BIN"
        -i "$SSH_KEY"
        -p "$SSH_PORT"
        -o BatchMode=yes
        -o IdentitiesOnly=yes
        -o ConnectTimeout=10
        -o StrictHostKeyChecking=yes
        -o "UserKnownHostsFile=${KNOWN_HOSTS}"
    )
    local rendered_command

    printf -v rendered_command '%q ' "${command_parts[@]}"
    printf '%s' "$rendered_command"
}


transfer_archive() {
    local archive_path="$1"
    local archive_name
    local remote_name
    local remote_directory
    local rsync_ssh_command

    archive_name="$(basename -- "$archive_path")"
    if [[ ! "$archive_name" =~ ^resource\.log-[0-9]{8}T[0-9]{6}\.gz$ ]]; then
        printf 'Unexpected archive name: %s\n' "$archive_name" >&2
        return 65
    fi

    remote_name="${SOURCE_ID}-${archive_name}"
    remote_directory="${REMOTE_STAGING_ROOT%/}/${SOURCE_ID}"
    rsync_ssh_command="$(build_rsync_ssh_command)"

    "$RSYNC_BIN" \
        -rt \
        --partial \
        --delay-updates \
        --checksum \
        --remove-source-files \
        --chmod=F440 \
        --timeout="$RSYNC_TIMEOUT_SECONDS" \
        -e "$rsync_ssh_command" \
        -- \
        "$archive_path" \
        "${REMOTE_USER}@${MONITORING_HOST}:${remote_directory}/${remote_name}"
}


validate_configuration

log_ops_create_directory "$ROTATED_DIR" 0750
log_ops_create_directory "$STATE_DIR" 0750
log_ops_create_directory "$(dirname -- "$STATUS_LOG")" 0750
log_ops_create_directory "$(dirname -- "$LOCK_FILE")" 0750
LAST_SUCCESS="$(log_ops_read_state "$LAST_SUCCESS_FILE")"
LAST_ERROR="$(log_ops_read_state "$LAST_ERROR_FILE")"

exec 9>"$LOCK_FILE"
if ! "$FLOCK_BIN" -n 9; then
    exit 0
fi
LOCK_ACQUIRED=1
trap emit_status EXIT

shopt -s nullglob
archives=("$ROTATED_DIR"/$ROTATED_GLOB)
shopt -u nullglob

for archive_path in "${archives[@]}"; do
    [[ -f "$archive_path" && ! -L "$archive_path" ]] || continue
    [[ "$(stat -c '%h' -- "$archive_path")" == "1" ]] || fail "archive_must_have_one_hardlink:$(basename -- "$archive_path")"

    if transfer_archive "$archive_path"; then
        LAST_SUCCESS="$(log_ops_utc_now)"
        LAST_ERROR=""
        RESULT="success"
    else
        transfer_exit_code=$?
        fail "rsync_failed:$(basename -- "$archive_path"):exit_${transfer_exit_code}"
    fi
done

# =============================================================================
# [END] Source EC2 daily rotated-log shipper
# =============================================================================
