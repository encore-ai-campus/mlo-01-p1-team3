#!/usr/bin/env bash

# =============================================================================
# [START] Shared resource-log archive library
# Purpose:
#   Provide validation, directory, state, and JSON status helpers shared by
#   the six source EC2 archive scripts and the Monitoring EC2 ingest script.
#   This file is sourced by other scripts and is not executed directly.
# =============================================================================


log_ops_source_ids() {
    printf '%s\n' \
        collector \
        mysql-primary \
        mysql-secondary \
        mongo-01 \
        mongo-02 \
        mongo-03
}


log_ops_validate_source_id() {
    case "$1" in
        collector|mysql-primary|mysql-secondary|mongo-01|mongo-02|mongo-03)
            return 0
            ;;
        *)
            printf 'Unsupported SOURCE_ID: %s\n' "$1" >&2
            return 2
            ;;
    esac
}

log_ops_utc_now() {
    date -u +"%Y-%m-%dT%H:%M:%SZ"
}


log_ops_require_executable() {
    local executable="$1"

    if [[ "$executable" == */* ]]; then
        [[ -x "$executable" ]] || {
            printf 'Required executable is missing or not executable: %s\n' "$executable" >&2
            return 127
        }
        return 0
    fi

    command -v "$executable" >/dev/null 2>&1 || {
        printf 'Required executable was not found in PATH: %s\n' "$executable" >&2
        return 127
    }
}


log_ops_validate_managed_directory() {
    local directory="$1"
    local normalized="${directory%/}"

    [[ -n "$normalized" ]] || normalized="/"
    [[ "$normalized" == /* ]] || {
        printf 'Managed directory must be absolute: %s\n' "$directory" >&2
        return 2
    }

    case "$normalized" in
        /|/bin|/boot|/dev|/etc|/home|/lib|/lib64|/media|/mnt|/opt|/proc|/root|/run|/sbin|/srv|/sys|/tmp|/usr|/var|/var/lib|/var/log|/var/spool)
            printf 'Refusing to manage a broad system directory: %s\n' "$directory" >&2
            return 2
            ;;
    esac

    [[ ! -L "$normalized" ]] || {
        printf 'Managed directory must not be a symbolic link: %s\n' "$directory" >&2
        return 2
    }
}


log_ops_create_directory() {
    local directory="$1"
    local mode="${2:-0750}"
    local owner="${3:-}"
    local group="${4:-}"
    local install_args=(-d -m "$mode")

    log_ops_validate_managed_directory "$directory"

    if [[ -n "$owner" ]]; then
        install_args+=(-o "$owner")
    fi
    if [[ -n "$group" ]]; then
        install_args+=(-g "$group")
    fi

    # Git Bash on Windows cannot always apply POSIX mode bits to temporary
    # directories. The fallback is intentionally opt-in and is only used by
    # the repository's non-production shell workflow test.
    if [[ "${LOG_OPS_ALLOW_MODE_FALLBACK:-0}" == "1" ]]; then
        if install "${install_args[@]}" -- "$directory" 2>/dev/null; then
            return 0
        fi
        mkdir -p -- "$directory"
        chmod "$mode" "$directory" 2>/dev/null || true
        return 0
    fi

    install "${install_args[@]}" -- "$directory"
}


log_ops_read_state() {
    local state_file="$1"
    local value=""

    if [[ -r "$state_file" ]]; then
        IFS= read -r value < "$state_file" || true
    fi

    printf '%s' "$value"
}


log_ops_write_state() {
    local state_file="$1"
    local value="$2"
    local state_dir
    local temporary_file

    state_dir="$(dirname -- "$state_file")"
    log_ops_create_directory "$state_dir" 0750
    temporary_file="$(mktemp "${state_file}.tmp.XXXXXX")"

    printf '%s\n' "$value" > "$temporary_file"
    chmod 0600 "$temporary_file"
    mv -f -- "$temporary_file" "$state_file"
}


log_ops_json_escape() {
    local value="$1"

    value=${value//\\/\\\\}
    value=${value//\"/\\\"}
    value=${value//$'\n'/\\n}
    value=${value//$'\r'/\\r}
    value=${value//$'\t'/\\t}

    printf '%s' "$value"
}


log_ops_json_string_or_null() {
    local value="${1:-}"

    if [[ -z "$value" ]]; then
        printf 'null'
        return 0
    fi

    printf '"%s"' "$(log_ops_json_escape "$value")"
}


log_ops_pending_count() {
    local directory="$1"
    local name_glob="$2"
    local file
    local count=0

    shopt -s nullglob
    for file in "$directory"/$name_glob; do
        [[ -f "$file" ]] || continue
        ((count += 1))
    done
    shopt -u nullglob

    printf '%s' "$count"
}


log_ops_oldest_pending() {
    local directory="$1"
    local name_glob="$2"
    local file
    local file_epoch
    local oldest_epoch=""

    shopt -s nullglob
    for file in "$directory"/$name_glob; do
        [[ -f "$file" ]] || continue
        file_epoch="$(stat -c '%Y' -- "$file")"
        if [[ -z "$oldest_epoch" || "$file_epoch" -lt "$oldest_epoch" ]]; then
            oldest_epoch="$file_epoch"
        fi
    done
    shopt -u nullglob

    if [[ -n "$oldest_epoch" ]]; then
        date -u -d "@${oldest_epoch}" +"%Y-%m-%dT%H:%M:%SZ"
    fi
}


log_ops_same_filesystem() {
    local left_path="$1"
    local right_path="$2"
    local left_device
    local right_device

    left_device="$(stat -c '%d' -- "$left_path")"
    right_device="$(stat -c '%d' -- "$right_path")"
    [[ "$left_device" == "$right_device" ]]
}


log_ops_write_status_record() {
    local status_log="$1"
    local component="$2"
    local source_id="$3"
    local result="$4"
    local pending_count="$5"
    local oldest_pending="$6"
    local last_success="$7"
    local last_error="$8"
    local level="INFO"
    local message="Log operation completed"

    if [[ "$result" == "failed" ]]; then
        level="ERROR"
        message="Log operation failed"
    elif [[ "$result" == "pending" || "$result" == "partial" ]]; then
        level="WARNING"
        message="Log operation completed with pending work"
    fi

    log_ops_create_directory "$(dirname -- "$status_log")" 0750
    printf \
        '{"ts":"%s","level":"%s","event_name":"resource_log_archive_status","message":"%s","component":"%s","source_id":"%s","result":"%s","pending_count":%s,"oldest_pending":%s,"last_success":%s,"last_error":%s}\n' \
        "$(log_ops_utc_now)" \
        "$level" \
        "$message" \
        "$(log_ops_json_escape "$component")" \
        "$(log_ops_json_escape "$source_id")" \
        "$(log_ops_json_escape "$result")" \
        "$pending_count" \
        "$(log_ops_json_string_or_null "$oldest_pending")" \
        "$(log_ops_json_string_or_null "$last_success")" \
        "$(log_ops_json_string_or_null "$last_error")" \
        >> "$status_log"
}


log_ops_emit_status() {
    log_ops_write_status_record "$@"
}


log_ops_load_config() {
    local config_file="$1"

    [[ -r "$config_file" ]] || {
        printf 'Configuration file is not readable: %s\n' "$config_file" >&2
        return 1
    }

    # shellcheck disable=SC1090
    source "$config_file"
}

# =============================================================================
# [END] Shared resource-log archive library
# =============================================================================
