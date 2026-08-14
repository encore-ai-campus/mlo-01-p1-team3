#!/usr/bin/env bash

# =============================================================================
# [TEST START] Six-source resource-log archive workflow
# Purpose:
#   Validate shell syntax, six Monitoring directory contracts, hourly rotation
#   invocation, daily rsync success/failure behavior, gzip validation, source
#   separation, duplicate handling, and conflict quarantine without AWS access.
# =============================================================================

set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OPS_DIR="${REPO_ROOT}/ops/logging"
TEST_TMP_DIR="$(mktemp -d)"
SOURCE_IDS=(collector mysql-primary mysql-secondary mongo-01 mongo-02 mongo-03)


cleanup() {
    case "$TEST_TMP_DIR" in
        /tmp/*)
            rm -rf -- "$TEST_TMP_DIR"
            ;;
        *)
            printf 'Refusing to remove unexpected test directory: %s\n' "$TEST_TMP_DIR" >&2
            ;;
    esac
}


assert_file_contains() {
    local file_path="$1"
    local expected_text="$2"

    grep -F -- "$expected_text" "$file_path" >/dev/null || {
        printf 'Expected text was not found. file=%s expected=%s\n' "$file_path" "$expected_text" >&2
        exit 1
    }
}


assert_path_exists() {
    local path="$1"

    [[ -e "$path" ]] || {
        printf 'Expected path does not exist: %s\n' "$path" >&2
        exit 1
    }
}


assert_path_missing() {
    local path="$1"

    [[ ! -e "$path" ]] || {
        printf 'Path should not exist: %s\n' "$path" >&2
        exit 1
    }
}


create_gzip() {
    local destination="$1"
    local content="$2"

    printf '%s\n' "$content" | gzip -c > "$destination"
}


trap cleanup EXIT

mkdir -p \
    "$TEST_TMP_DIR/bin" \
    "$TEST_TMP_DIR/source/outbox" \
    "$TEST_TMP_DIR/source/state" \
    "$TEST_TMP_DIR/source/status" \
    "$TEST_TMP_DIR/monitoring/incoming" \
    "$TEST_TMP_DIR/monitoring/archive" \
    "$TEST_TMP_DIR/monitoring/quarantine" \
    "$TEST_TMP_DIR/monitoring/state" \
    "$TEST_TMP_DIR/monitoring/status" \
    "$TEST_TMP_DIR/keys"

touch "$TEST_TMP_DIR/keys/private_key" "$TEST_TMP_DIR/keys/known_hosts"
chmod 0600 "$TEST_TMP_DIR/keys/private_key" "$TEST_TMP_DIR/keys/known_hosts"

cat > "$TEST_TMP_DIR/bin/fake-flock" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

cat > "$TEST_TMP_DIR/bin/fake-logrotate" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
printf '%s\n' "$*" > "$FAKE_LOGROTATE_ARGUMENTS"
EOF

cat > "$TEST_TMP_DIR/bin/fake-rsync" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${FAKE_RSYNC_FAIL:-0}" == "1" ]]; then
    exit 23
fi

arguments=("$@")
argument_count=${#arguments[@]}
source_file="${arguments[$((argument_count - 2))]}"
remote_target="${arguments[$((argument_count - 1))]}"
remote_path="${remote_target#*:}"

case "$remote_path" in
    "${FAKE_REMOTE_DECLARED_ROOT}"/*)
        relative_path="${remote_path#"${FAKE_REMOTE_DECLARED_ROOT}"/}"
        ;;
    *)
        printf 'Unexpected fake remote target: %s\n' "$remote_path" >&2
        exit 64
        ;;
esac

local_target="${FAKE_REMOTE_ROOT}/${relative_path}"
mkdir -p -- "$(dirname -- "$local_target")"
temporary_target="$(dirname -- "$local_target")/.$(basename -- "$local_target").partial"
cp -- "$source_file" "$temporary_target"
mv -- "$temporary_target" "$local_target"
rm -f -- "$source_file"
EOF

chmod 0750 "$TEST_TMP_DIR/bin/fake-flock" "$TEST_TMP_DIR/bin/fake-logrotate" "$TEST_TMP_DIR/bin/fake-rsync"

cat > "$TEST_TMP_DIR/source-log-archive.env" <<EOF
SOURCE_ID=collector
ROTATED_DIR=$TEST_TMP_DIR/source/outbox
ROTATED_GLOB=resource.log-*.gz
LOCK_FILE=$TEST_TMP_DIR/source/archive.lock
STATE_DIR=$TEST_TMP_DIR/source/state
STATUS_LOG=$TEST_TMP_DIR/source/status/archive-status.jsonl
LOGROTATE_BIN=$TEST_TMP_DIR/bin/fake-logrotate
LOGROTATE_CONFIG=$TEST_TMP_DIR/resource-logrotate.conf
LOGROTATE_STATE=$TEST_TMP_DIR/source/logrotate.status
FLOCK_BIN=$TEST_TMP_DIR/bin/fake-flock
RSYNC_BIN=$TEST_TMP_DIR/bin/fake-rsync
SSH_BIN=/usr/bin/true
RSYNC_TIMEOUT_SECONDS=30
SSH_PORT=22
SSH_KEY=$TEST_TMP_DIR/keys/private_key
KNOWN_HOSTS=$TEST_TMP_DIR/keys/known_hosts
REMOTE_USER=logship
MONITORING_HOST=10.0.10.40
REMOTE_STAGING_ROOT=/var/spool/car-market/incoming
LOG_OPS_ALLOW_MODE_FALLBACK=1
EOF

cat > "$TEST_TMP_DIR/monitoring-log-archive.env" <<EOF
STAGING_ROOT=$TEST_TMP_DIR/monitoring/incoming
ARCHIVE_ROOT=$TEST_TMP_DIR/monitoring/archive
QUARANTINE_ROOT=$TEST_TMP_DIR/monitoring/quarantine
STATE_DIR=$TEST_TMP_DIR/monitoring/state
STATUS_LOG=$TEST_TMP_DIR/monitoring/status/archive-ingest-status.jsonl
LOCK_FILE=$TEST_TMP_DIR/monitoring/archive.lock
FLOCK_BIN=$TEST_TMP_DIR/bin/fake-flock
GZIP_BIN=/usr/bin/gzip
STAGING_OWNER=logship
STAGING_GROUP=logship
STAGING_ROOT_OWNER=root
STAGING_ROOT_GROUP=logship
ARCHIVE_OWNER=root
ARCHIVE_GROUP=root
ARCHIVE_FILE_MODE=0640
OWNERSHIP_ENABLED=0
LOG_OPS_ALLOW_MODE_FALLBACK=1
EOF

printf '%s\n' '# fake logrotate configuration' > "$TEST_TMP_DIR/resource-logrotate.conf"

# All executable shell files must parse before behavioral tests begin.
bash -n \
    "$OPS_DIR/lib_log_ops.sh" \
    "$OPS_DIR/rotate_resource_log.sh" \
    "$OPS_DIR/ship_rotated_logs.sh" \
    "$OPS_DIR/prepare_monitoring_archive.sh" \
    "$OPS_DIR/ingest_rotated_logs.sh"

# Monitoring preparation must create exactly the six contracted role trees.
CONFIG_FILE="$TEST_TMP_DIR/monitoring-log-archive.env" \
LOG_OPS_LIB_FILE="$OPS_DIR/lib_log_ops.sh" \
bash "$OPS_DIR/prepare_monitoring_archive.sh"

for source_id in "${SOURCE_IDS[@]}"; do
    assert_path_exists "$TEST_TMP_DIR/monitoring/incoming/$source_id"
    assert_path_exists "$TEST_TMP_DIR/monitoring/archive/$source_id"
    assert_path_exists "$TEST_TMP_DIR/monitoring/quarantine/$source_id"
done

# The hourly launcher must pass the dedicated state and config to logrotate.
FAKE_LOGROTATE_ARGUMENTS="$TEST_TMP_DIR/logrotate-arguments.txt" \
CONFIG_FILE="$TEST_TMP_DIR/source-log-archive.env" \
LOG_OPS_LIB_FILE="$OPS_DIR/lib_log_ops.sh" \
bash "$OPS_DIR/rotate_resource_log.sh"

assert_file_contains "$TEST_TMP_DIR/logrotate-arguments.txt" "--state $TEST_TMP_DIR/source/logrotate.status"
assert_file_contains "$TEST_TMP_DIR/logrotate-arguments.txt" "$TEST_TMP_DIR/resource-logrotate.conf"
assert_path_exists "$TEST_TMP_DIR/source/state/last_rotation_success"

# Collector: a successful transfer removes the source gzip and prefixes the
# remote filename with SOURCE_ID before Monitoring ingestion.
collector_source="$TEST_TMP_DIR/source/outbox/resource.log-20260813T010700.gz"
collector_staging="$TEST_TMP_DIR/monitoring/incoming/collector/collector-resource.log-20260813T010700.gz"
collector_archive="$TEST_TMP_DIR/monitoring/archive/collector/collector-resource.log-20260813T010700.gz"
create_gzip "$collector_source" 'collector sample'

FAKE_REMOTE_ROOT="$TEST_TMP_DIR/monitoring/incoming" \
FAKE_REMOTE_DECLARED_ROOT=/var/spool/car-market/incoming \
CONFIG_FILE="$TEST_TMP_DIR/source-log-archive.env" \
LOG_OPS_LIB_FILE="$OPS_DIR/lib_log_ops.sh" \
bash "$OPS_DIR/ship_rotated_logs.sh"

assert_path_missing "$collector_source"
assert_path_exists "$collector_staging"
assert_file_contains "$TEST_TMP_DIR/source/status/archive-status.jsonl" '"source_id":"collector"'
assert_file_contains "$TEST_TMP_DIR/source/status/archive-status.jsonl" '"result":"success"'

CONFIG_FILE="$TEST_TMP_DIR/monitoring-log-archive.env" \
LOG_OPS_LIB_FILE="$OPS_DIR/lib_log_ops.sh" \
bash "$OPS_DIR/ingest_rotated_logs.sh"

assert_path_missing "$collector_staging"
assert_path_exists "$collector_archive"
gzip -t -- "$collector_archive"

# All six roles must remain isolated in their own final directories.
index=1
for source_id in "${SOURCE_IDS[@]}"; do
    timestamp="20260813T04$(printf '%02d' "$index")07"
    staged_name="${source_id}-resource.log-${timestamp}.gz"
    create_gzip "$TEST_TMP_DIR/monitoring/incoming/$source_id/$staged_name" "$source_id sample"
    ((index += 1))
done

CONFIG_FILE="$TEST_TMP_DIR/monitoring-log-archive.env" \
LOG_OPS_LIB_FILE="$OPS_DIR/lib_log_ops.sh" \
bash "$OPS_DIR/ingest_rotated_logs.sh"

index=1
for source_id in "${SOURCE_IDS[@]}"; do
    timestamp="20260813T04$(printf '%02d' "$index")07"
    archived_name="${source_id}-resource.log-${timestamp}.gz"
    assert_path_exists "$TEST_TMP_DIR/monitoring/archive/$source_id/$archived_name"
    assert_path_missing "$TEST_TMP_DIR/monitoring/incoming/$source_id/$archived_name"
    ((index += 1))
done

# A failed rsync must leave the local gzip available for the next daily retry.
retry_source="$TEST_TMP_DIR/source/outbox/resource.log-20260813T060700.gz"
create_gzip "$retry_source" 'retry sample'

if FAKE_RSYNC_FAIL=1 \
    FAKE_REMOTE_ROOT="$TEST_TMP_DIR/monitoring/incoming" \
    FAKE_REMOTE_DECLARED_ROOT=/var/spool/car-market/incoming \
    CONFIG_FILE="$TEST_TMP_DIR/source-log-archive.env" \
    LOG_OPS_LIB_FILE="$OPS_DIR/lib_log_ops.sh" \
    bash "$OPS_DIR/ship_rotated_logs.sh" >/dev/null 2>&1; then
    printf 'Expected rsync failure did not occur\n' >&2
    exit 1
fi

assert_path_exists "$retry_source"
assert_file_contains "$TEST_TMP_DIR/source/status/archive-status.jsonl" '"result":"failed"'
assert_file_contains "$TEST_TMP_DIR/source/status/archive-status.jsonl" '"pending_count":1'

# A role outside the six-value contract must fail before any transfer attempt.
sed 's/^SOURCE_ID=collector$/SOURCE_ID=unknown-role/' \
    "$TEST_TMP_DIR/source-log-archive.env" \
    > "$TEST_TMP_DIR/invalid-source-log-archive.env"

if FAKE_REMOTE_ROOT="$TEST_TMP_DIR/monitoring/incoming" \
    FAKE_REMOTE_DECLARED_ROOT=/var/spool/car-market/incoming \
    CONFIG_FILE="$TEST_TMP_DIR/invalid-source-log-archive.env" \
    LOG_OPS_LIB_FILE="$OPS_DIR/lib_log_ops.sh" \
    bash "$OPS_DIR/ship_rotated_logs.sh" >/dev/null 2>&1; then
    printf 'Expected invalid SOURCE_ID failure did not occur\n' >&2
    exit 1
fi

assert_path_exists "$retry_source"

# Corrupt gzip data is quarantined and cannot enter the final archive.
invalid_name="mongo-01-resource.log-20260813T070700.gz"
printf '%s\n' 'not gzip data' > "$TEST_TMP_DIR/monitoring/incoming/mongo-01/$invalid_name"

CONFIG_FILE="$TEST_TMP_DIR/monitoring-log-archive.env" \
LOG_OPS_LIB_FILE="$OPS_DIR/lib_log_ops.sh" \
bash "$OPS_DIR/ingest_rotated_logs.sh" >/dev/null 2>&1

assert_path_missing "$TEST_TMP_DIR/monitoring/incoming/mongo-01/$invalid_name"
assert_path_missing "$TEST_TMP_DIR/monitoring/archive/mongo-01/$invalid_name"
compgen -G "$TEST_TMP_DIR/monitoring/quarantine/mongo-01/${invalid_name}.invalid_gzip-*" >/dev/null
assert_file_contains "$TEST_TMP_DIR/monitoring/status/archive-ingest-status.jsonl" '"result":"partial"'

# A staging hard link is quarantined before chmod/chown or gzip processing.
hardlink_target="$TEST_TMP_DIR/hardlink-target.gz"
hardlink_name="mongo-02-resource.log-20260813T075700.gz"
create_gzip "$hardlink_target" 'hardlink payload'
ln "$hardlink_target" "$TEST_TMP_DIR/monitoring/incoming/mongo-02/$hardlink_name"

CONFIG_FILE="$TEST_TMP_DIR/monitoring-log-archive.env" \
LOG_OPS_LIB_FILE="$OPS_DIR/lib_log_ops.sh" \
bash "$OPS_DIR/ingest_rotated_logs.sh"

assert_path_exists "$hardlink_target"
assert_path_missing "$TEST_TMP_DIR/monitoring/incoming/mongo-02/$hardlink_name"
assert_path_missing "$TEST_TMP_DIR/monitoring/archive/mongo-02/$hardlink_name"
compgen -G "$TEST_TMP_DIR/monitoring/quarantine/mongo-02/${hardlink_name}.multiple_hardlinks-*" >/dev/null

# A different payload with an existing filename is quarantined; the existing
# final archive remains unchanged.
conflict_name="mysql-primary-resource.log-20260813T080700.gz"
conflict_archive="$TEST_TMP_DIR/monitoring/archive/mysql-primary/$conflict_name"
conflict_staging="$TEST_TMP_DIR/monitoring/incoming/mysql-primary/$conflict_name"
create_gzip "$conflict_archive" 'original payload'
create_gzip "$conflict_staging" 'different payload'
original_checksum="$(sha256sum "$conflict_archive" | awk '{print $1}')"

CONFIG_FILE="$TEST_TMP_DIR/monitoring-log-archive.env" \
LOG_OPS_LIB_FILE="$OPS_DIR/lib_log_ops.sh" \
bash "$OPS_DIR/ingest_rotated_logs.sh"

assert_path_missing "$conflict_staging"
[[ "$(sha256sum "$conflict_archive" | awk '{print $1}')" == "$original_checksum" ]]
compgen -G "$TEST_TMP_DIR/monitoring/quarantine/mysql-primary/${conflict_name}.name_conflict-*" >/dev/null

# Static schedule and retention contracts must remain explicit.
assert_file_contains "$OPS_DIR/car-market-resource-logrotate.cron" '7 * * * * root'
assert_file_contains "$OPS_DIR/car-market-daily-logship.cron" '15 2 * * * root'
assert_file_contains "$OPS_DIR/car-market-daily-log-ingest.cron" '45 2 * * * root'
assert_file_contains "$OPS_DIR/car-market-resource.logrotate.conf" 'hourly'
assert_file_contains "$OPS_DIR/car-market-resource.logrotate.conf" 'rotate 168'
assert_file_contains "$OPS_DIR/car-market-resource.logrotate.conf" 'nocreate'

printf 'PASS: six-source hourly rotation and daily Monitoring archive workflow\n'

# =============================================================================
# [TEST END] Six-source resource-log archive workflow
# =============================================================================
