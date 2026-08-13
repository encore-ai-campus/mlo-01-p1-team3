# EC2 6대 `resource.log` 시간별 회전 및 일별 중앙 보관

이 디렉터리는 `car-market-monitoring-guide.md` 2번의 실시간 모니터링 흐름을 유지하면서, 각 EC2에 누적되는 `/var/log/car-market/resource.log`의 과거 파일을 Monitoring EC2에 중앙 보관하기 위한 운영 파일 모음입니다.

실시간 흐름과 보관 흐름은 서로 독립적입니다.

```text
[실시간 상태 표시 - 기존 동작 유지]
각 EC2 collect_metrics.sh
  └─ HTTP POST → Monitoring 10.0.10.40:5000 → Flask/Dashboard

[이력 파일 보관 - 이번 구현]
각 EC2 /var/log/car-market/resource.log
  └─ 매시 07분 logrotate
       └─ /var/log/car-market/archive-outbox/resource.log-YYYYMMDDTHHMMSS.gz
            └─ 매일 02:15 rsync over SSH
                 └─ Monitoring staging/<source-id>/
                      └─ 매일 02:45 gzip 검증 및 적재
                           └─ Monitoring archive/<source-id>/
```

## 서버 역할과 `SOURCE_ID`

각 소스 서버의 `/etc/car-market/source-log-archive.env`에는 아래 값을 정확히 하나 지정합니다.

| 서버 | Private IP | `SOURCE_ID` | Monitoring 최종 디렉터리 |
|---|---:|---|---|
| Collector | `10.0.10.10` | `collector` | `/var/log/car-market/archive/collector/` |
| MySQL Primary | `10.0.10.20` | `mysql-primary` | `/var/log/car-market/archive/mysql-primary/` |
| MySQL Secondary | `10.0.20.20` | `mysql-secondary` | `/var/log/car-market/archive/mysql-secondary/` |
| MongoDB 01 | `10.0.10.30` | `mongo-01` | `/var/log/car-market/archive/mongo-01/` |
| MongoDB 02 | `10.0.20.30` | `mongo-02` | `/var/log/car-market/archive/mongo-02/` |
| MongoDB 03 | `10.0.10.31` | `mongo-03` | `/var/log/car-market/archive/mongo-03/` |

Monitoring 서버에서 디렉터리가 없으면 `prepare_monitoring_archive.sh`와 `ingest_rotated_logs.sh`가 다음 구조를 생성합니다.

```text
/var/spool/car-market/incoming/
├── collector/
├── mysql-primary/
├── mysql-secondary/
├── mongo-01/
├── mongo-02/
└── mongo-03/

/var/log/car-market/archive/
├── collector/
├── mysql-primary/
├── mysql-secondary/
├── mongo-01/
├── mongo-02/
└── mongo-03/

/var/spool/car-market/quarantine/
├── collector/
├── mysql-primary/
├── mysql-secondary/
├── mongo-01/
├── mongo-02/
└── mongo-03/
```

전송 파일명에도 `SOURCE_ID`를 붙입니다. 예를 들어 Collector 파일은 `collector-resource.log-20260813T010700.gz`가 되므로, 잘못된 디렉터리로 복사되더라도 출처를 식별할 수 있습니다.

## 포함 파일

| 파일 | 배포 대상 | 기능 |
|---|---|---|
| `lib_log_ops.sh` | 소스 6대, Monitoring | 공통 검증·상태 기록 함수 |
| `source-log-archive.env.example` | 소스 6대 | 서버 역할, SSH, 전송 경로 설정 예시 |
| `car-market-resource.logrotate.conf` | 소스 6대 | `resource.log` 시간별 압축, 최대 168개 보관 |
| `rotate_resource_log.sh` | 소스 6대 | 전용 state·lock으로 logrotate 실행 |
| `ship_rotated_logs.sh` | 소스 6대 | 일 1회 rsync 전송, 성공 파일만 로컬 삭제 |
| `car-market-resource-logrotate.cron` | 소스 6대 | 매시 07분 회전 cron |
| `car-market-daily-logship.cron` | 소스 6대 | 매일 02:15 전송 cron |
| `monitoring-log-archive.env.example` | Monitoring | staging/archive/권한 설정 예시 |
| `prepare_monitoring_archive.sh` | Monitoring | 6개 역할별 디렉터리 생성 |
| `ingest_rotated_logs.sh` | Monitoring | gzip 검증, 충돌 검사, 역할별 최종 적재 |
| `car-market-daily-log-ingest.cron` | Monitoring | 매일 02:45 적재 cron |

## 핵심 안전 동작

- 문서에 적힌 `metrics_loop.sh → collect_metrics.sh` 반복 호출처럼 각 측정이 로그 파일을 열고 닫는 구조를 전제로 rename 방식 회전을 사용합니다. `copytruncate`를 사용하지 않아 복사와 truncate 사이의 로그 유실 구간을 만들지 않습니다. 실제 배포 전에는 아래의 열린 파일 핸들 검사를 반드시 수행합니다.
- logrotate 후 활성 파일을 미리 만들지 않는 `nocreate`를 사용합니다. 다음 `collect_metrics.sh` 실행이 기존 서비스 계정으로 새 `resource.log`를 생성하므로 임의의 owner 하드코딩으로 쓰기가 막히지 않습니다.
- 시간별 회전과 일별 전송은 같은 `flock` 파일을 사용하여 압축 중인 파일을 rsync가 읽지 않습니다.
- rsync는 `StrictHostKeyChecking=yes`와 전용 `known_hosts`를 사용합니다. `StrictHostKeyChecking=no`는 사용하지 않습니다. 파일 내용 checksum도 비교하며, 수신 완료 파일은 쓰기 불가 모드로 둡니다.
- 전송에 성공한 gzip만 `--remove-source-files`로 삭제합니다. 네트워크·SSH·권한 오류가 나면 소스 outbox에 남아 다음 날 다시 시도합니다.
- Monitoring은 일반 파일·단일 hard link·`gzip -t`를 모두 통과한 파일만 최종 보관합니다. 심볼릭 링크, 깨진 gzip, 동일 파일명의 내용 충돌은 source별 `quarantine`으로 이동하며 기존 파일을 덮어쓰지 않습니다.
- Monitoring staging의 최상위 디렉터리는 `root` 소유로 유지하고 하위 source 디렉터리만 `logship`이 쓰도록 하여 source 디렉터리 자체가 교체되는 것을 막습니다.
- `SOURCE_ID`는 여섯 값만 허용하므로 설정 오타나 임의 경로 주입으로 다른 서버 디렉터리에 적재할 수 없습니다.

## 1. Monitoring EC2 선행 설치

소스 서버가 전송하기 전에 Monitoring 서버를 먼저 준비합니다.

```bash
# =============================================================================
# [START] Monitoring EC2 파일 설치 및 역할별 디렉터리 생성
# Function: 공통 라이브러리·적재 스크립트·환경파일·cron을 운영 경로에 설치
# =============================================================================
sudo useradd --system --create-home --shell /bin/bash logship 2>/dev/null || true
sudo install -d -m 0750 /usr/local/lib/car-market /etc/car-market
sudo install -m 0640 ops/logging/monitoring-log-archive.env.example /etc/car-market/monitoring-log-archive.env
sudo install -m 0750 ops/logging/lib_log_ops.sh ops/logging/prepare_monitoring_archive.sh ops/logging/ingest_rotated_logs.sh /usr/local/lib/car-market/
sudo install -m 0644 ops/logging/car-market-daily-log-ingest.cron /etc/cron.d/car-market-daily-log-ingest
sudo /usr/local/lib/car-market/prepare_monitoring_archive.sh
# =============================================================================
# [END] Monitoring EC2 파일 설치 및 역할별 디렉터리 생성
# =============================================================================
```

`logship` 계정의 `~/.ssh/authorized_keys`에는 각 소스 EC2에서 생성한 공개키를 등록합니다. 운영 환경에서는 서버별 키를 각각 발급하고, 가능하면 각 키의 rsync 목적지를 해당 `SOURCE_ID` staging 디렉터리로 제한합니다.

## 2. 각 소스 EC2 설치

아래 작업을 Collector, MySQL 2대, MongoDB 3대에서 반복하고 `SOURCE_ID`만 서버 역할에 맞게 변경합니다.

```bash
# =============================================================================
# [START] 소스 EC2 회전·전송 파일 설치
# Function: resource.log 시간별 회전과 일별 SSH/rsync 전송을 활성화
# =============================================================================
sudo install -d -m 0750 /usr/local/lib/car-market /etc/car-market /etc/car-market/keys
sudo install -m 0750 ops/logging/lib_log_ops.sh ops/logging/rotate_resource_log.sh ops/logging/ship_rotated_logs.sh /usr/local/lib/car-market/
sudo install -m 0640 ops/logging/source-log-archive.env.example /etc/car-market/source-log-archive.env
sudo install -m 0644 ops/logging/car-market-resource.logrotate.conf /etc/car-market/resource-logrotate.conf
sudo install -m 0644 ops/logging/car-market-resource-logrotate.cron /etc/cron.d/car-market-resource-logrotate
sudo install -m 0644 ops/logging/car-market-daily-logship.cron /etc/cron.d/car-market-daily-logship
sudo chmod 0600 /etc/car-market/keys/resource-logship_ed25519
# =============================================================================
# [END] 소스 EC2 회전·전송 파일 설치
# =============================================================================
```

`/etc/car-market/source-log-archive.env`에서 반드시 확인할 값은 다음과 같습니다.

```bash
# =============================================================================
# [START] 소스 서버별 필수 설정
# Function: 서버 역할과 Monitoring SSH 접속 정보를 지정
# =============================================================================
SOURCE_ID=collector
SSH_KEY=/etc/car-market/keys/resource-logship_ed25519
KNOWN_HOSTS=/etc/car-market/known_hosts
REMOTE_USER=logship
MONITORING_HOST=10.0.10.40
# =============================================================================
# [END] 소스 서버별 필수 설정
# =============================================================================
```

Windows에서 파일을 복사했다면 EC2에서 CRLF 여부를 확인하고 필요할 때만 `dos2unix`를 적용합니다.

## 3. SSH 및 보안그룹 조건

기존 실시간 Flask 전송용 TCP 5000 규칙은 그대로 유지합니다. 파일 보관 흐름에는 추가로 다음 연결이 필요합니다.

```text
Source: Collector/MySQL/MongoDB 서버의 Security Group
Target: Monitoring EC2 Security Group
Port: TCP 22
Direction: 소스 6대 → Monitoring
Address: Monitoring private IP 10.0.10.40
```

각 소스의 `/etc/car-market/known_hosts`에는 Monitoring 호스트키를 저장해야 합니다. `ssh-keyscan` 결과는 곧바로 신뢰하지 말고 Monitoring 서버 콘솔의 실제 SSH host key fingerprint와 대조한 뒤 등록합니다.

## 4. 수동 검증 순서

먼저 Monitoring에서 6개 디렉터리를 확인합니다.

```bash
# =============================================================================
# [START] Monitoring 디렉터리 검증
# Function: 6개 source별 staging과 최종 archive 생성 여부 확인
# =============================================================================
sudo /usr/local/lib/car-market/prepare_monitoring_archive.sh
sudo find /var/spool/car-market/incoming -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort
sudo find /var/log/car-market/archive -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort
# =============================================================================
# [END] Monitoring 디렉터리 검증
# =============================================================================
```

소스 EC2에서는 실제 강제 회전 전에 logrotate 설정을 debug 모드로 확인합니다. `-d`는 파일을 변경하지 않습니다.

```bash
# =============================================================================
# [START] 소스 logrotate 설정 비파괴 검증
# Function: resource.log 규칙과 권한·경로 오류를 실제 회전 없이 확인
# =============================================================================
sudo /usr/sbin/logrotate -d -s /var/lib/car-market/resource-logrotate.status /etc/car-market/resource-logrotate.conf
# =============================================================================
# [END] 소스 logrotate 설정 비파괴 검증
# =============================================================================
```

rename 회전 전제도 확인합니다. `lsof` 결과에 `resource.log`를 계속 잡고 있는 장기 실행 프로세스가 없어야 하며, 회전 후 새 파일을 생성할 서비스 계정이 `/var/log/car-market`에 쓸 수 있어야 합니다.

```bash
# =============================================================================
# [START] 활성 로그 파일 핸들·생성 권한 확인
# Function: rename 회전 후 이전 inode에 계속 기록되거나 새 파일 생성이 막히는지 사전 점검
# =============================================================================
sudo lsof /var/log/car-market/resource.log || true
systemctl cat car-market-metrics | grep -E '^User=' || true
sudo test -w /var/log/car-market && echo 'root can create resource.log'
# =============================================================================
# [END] 활성 로그 파일 핸들·생성 권한 확인
# =============================================================================
```

`lsof`에서 `metrics_loop.sh` 같은 장기 실행 프로세스가 파일을 계속 열고 있으면 현재 rename+compress 규칙을 적용하면 안 됩니다. 그 경우 실제 `collect_metrics.sh` 구현에 맞춰 reopen/restart 또는 `copytruncate`의 손실 위험을 검토한 별도 규칙이 필요합니다.

운영 전 1회 smoke test에서는 테스트 로그를 추가한 뒤 강제 회전, 전송, Monitoring 적재 순서로 확인합니다. 실제 운영 로그에 테스트 행을 넣을 수 있는지 팀 정책을 먼저 확인해야 합니다.

```bash
# =============================================================================
# [START] EC2 간 보관 흐름 smoke test
# Function: 소스 강제 회전·전송 후 Monitoring 역할별 최종 적재 확인
# =============================================================================
# Source EC2
sudo /usr/sbin/logrotate -f -s /var/lib/car-market/resource-logrotate.status /etc/car-market/resource-logrotate.conf
sudo /usr/local/lib/car-market/ship_rotated_logs.sh

# Monitoring EC2
sudo /usr/local/lib/car-market/ingest_rotated_logs.sh
sudo find /var/log/car-market/archive -type f -name '*.gz' -print
# =============================================================================
# [END] EC2 간 보관 흐름 smoke test
# =============================================================================
```

cron 설치 후에는 Amazon Linux 기준으로 `crond`가 실행 중인지 확인합니다.

```bash
sudo systemctl is-active crond
sudo systemctl reload crond
```

cron 시각은 OS의 시스템 시간대를 따릅니다. `monitor.env`의 `TIMEZONE=Asia/Seoul`은 로그 문자열의 시간대일 뿐 cron 시간대를 바꾸지 않으므로 `timedatectl`도 확인해야 합니다.

## 5. 상태 및 장애 확인

소스별 전송 상태는 다음 파일에 JSONL로 하루 한 줄씩 기록됩니다.

```text
/var/log/car-market/archive-status.jsonl
/var/lib/car-market/resource-log-archive/last_ship_success
/var/lib/car-market/resource-log-archive/last_ship_error
/var/lib/car-market/resource-log-archive/last_rotation_success
/var/lib/car-market/resource-log-archive/last_rotation_error
```

Monitoring 적재 상태는 다음에 기록됩니다.

```text
/var/log/car-market/archive-ingest-status.jsonl
/var/lib/car-market/monitoring-log-archive/last_ingest_success
/var/lib/car-market/monitoring-log-archive/last_ingest_error
```

`pending_count > 0`, 오래된 `oldest_pending`, 비어 있지 않은 `last_error`는 SSH·네트워크·권한·디스크 오류를 확인해야 한다는 신호입니다.

## 6. 보관 기간과 남은 운영 결정

소스 EC2의 `rotate 168`은 시간별 압축 파일을 최대 7일 보존하는 안전망입니다. 정상 전송 파일은 다음 일별 전송 직후 삭제되므로 평상시에는 약 24시간분만 남습니다. 전송 장애가 7일 이상 계속되면 logrotate가 가장 오래된 파일을 제거할 수 있으므로 상태 알림이 필요합니다.

Monitoring 최종 archive에는 자동 삭제를 넣지 않았습니다. 중앙 보관 기간이 정해지지 않은 상태에서 파일을 임의 삭제하지 않기 위한 선택입니다. Monitoring 디스크도 결국 증가하므로 팀에서 30일·90일 등 보관 기간과 별도 백업 위치를 정한 뒤 retention 작업을 추가해야 합니다.

이번 설정은 문서 2번의 공통 `/var/log/car-market/resource.log`만 대상으로 합니다. MySQL error/slow log, MongoDB `mongod.log`, Collector JSONL 업무 로그까지 회전하려면 각 프로세스의 reopen 방식과 보존 계약이 달라 별도 logrotate 규칙이 필요합니다.

## 7. 저장소 로컬 검증

실제 AWS 연결 없이 shell 흐름을 검증하는 테스트는 프로젝트 루트에서 실행합니다.

```bash
# =============================================================================
# [START] 로컬 shell 모듈 테스트
# Function: 문법, 6개 디렉터리, 전송 성공/재시도, gzip·충돌 격리를 검증
# =============================================================================
bash tests/test_ops_logging.sh
# =============================================================================
# [END] 로컬 shell 모듈 테스트
# =============================================================================
```

로컬 테스트는 실제 Security Group, SSH host key, EC2 계정 권한, 실제 cron 실행을 검증하지 못합니다. 이 네 항목은 위의 EC2 smoke test에서 최종 확인합니다.
