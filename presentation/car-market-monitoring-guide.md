# Car Market Monitoring 구성 문서 — 로컬 검증 기준

## 1. 문서 목적 및 현재 상태

본 문서는 Car Market 프로젝트의 시스템 자원 모니터링과 로그 중앙 보관 아키텍처를 정리한 문서입니다.

현재 상태는 다음과 같습니다.

| 구분 | 상태 |
|---|---|
| 로컬 운영 모듈 구현 | 완료 |
| 로컬 shell 문법 및 격리 통합 테스트 | 완료 |
| 실제 EC2 배포 | TODO |
| AWS Security Group / SSH 키 설정 | TODO |
| EC2 cron 및 systemd 활성화 | TODO |
| 실제 Monitoring Dashboard 운영 검증 | TODO |

즉, 이 문서의 EC2 구성은 **최종 목표 아키텍처**이며, 현재 완료 기준은 로컬 환경에서 운영 스크립트의 동작 계약을 검증한 상태입니다.

## 2. 목표 아키텍처

대상 서버는 다음 6대입니다.

| 구분 | 목표 Private IP | 역할 |
|---|---:|---|
| Collector | `10.0.10.10` | 크롤링·수집 및 DB 적재 |
| MySQL Primary | `10.0.10.20` | MySQL Primary |
| MySQL Secondary | `10.0.20.20` | MySQL Replica |
| MongoDB 01 | `10.0.10.30` | MongoDB Replica Set Member |
| MongoDB 02 | `10.0.20.30` | MongoDB Replica Set Member |
| MongoDB 03 | `10.0.10.31` | MongoDB Replica Set Member |

목표 Monitoring 서버는 `10.0.10.40`, Bastion 서버는 `10.0.1.10`입니다.

```text
[목표: 실시간 시스템 자원 모니터링]
각 EC2
  └─ collect_metrics.sh
       ├─ CPU / RAM / DISK 측정
       ├─ /var/log/car-market/resource.log 기록
       └─ Monitoring Flask API로 HTTP POST

[현재 로컬 검증 완료: 로그 이력 중앙 보관]
각 EC2 resource.log
  └─ 시간별 logrotate + gzip
       └─ 일 1회 rsync over SSH
            └─ Monitoring 역할별 archive 디렉터리 보관
```

실시간 Flask API Push와 로그 이력 파일 보관은 별도 흐름입니다.

## 3. 로컬 구현 및 검증 완료 항목

로컬에서 구현·검증한 운영 모듈은 프로젝트의 `ops/logging/`에 있습니다.

| 기능 | 구현 파일 | 로컬 검증 결과 |
|---|---|---|
| 시간별 resource.log 회전 호출 | `rotate_resource_log.sh` | 통과 |
| 일별 gzip 로그 전송 | `ship_rotated_logs.sh` | 통과 |
| Monitoring 수신 디렉터리 준비 | `prepare_monitoring_archive.sh` | 통과 |
| Monitoring 역할별 최종 적재 | `ingest_rotated_logs.sh` | 통과 |
| 전송 실패 시 재시도 | `test_ops_logging.sh` | 통과 |
| 손상 gzip / 충돌 파일 격리 | `test_ops_logging.sh` | 통과 |

로컬 검증 명령:

```bash
bash -n ops/logging/*.sh tests/test_ops_logging.sh
bash tests/test_ops_logging.sh
```

검증 결과:

```text
PASS: six-source hourly rotation and daily Monitoring archive workflow
```

### 역할별 최종 보관 구조

```text
/var/log/car-market/archive/
├── collector/
├── mysql-primary/
├── mysql-secondary/
├── mongo-01/
├── mongo-02/
└── mongo-03/
```

전송 성공 파일만 소스에서 삭제하고, 네트워크 또는 인증 오류 시 파일은 소스 outbox에 남아 다음 실행에서 재시도합니다. 손상 gzip, 심볼릭 링크, 다중 hard link, 동일 이름·다른 내용 파일은 Monitoring quarantine 디렉터리로 격리합니다.

## 4. 목표 EC2 운영 파일

다음 경로는 실제 EC2 적용 시 사용할 **목표 운영 경로**이며, 아직 전체 서버에 적용 완료된 상태가 아닙니다.

| 구분 | 목표 경로 | 용도 |
|---|---|---|
| source 공통 설정 | `/etc/car-market/source-log-archive.env` | 서버 역할·SSH·전송 설정 |
| source 회전 설정 | `/etc/car-market/resource-logrotate.conf` | 시간별 resource.log 회전 |
| source 실행 스크립트 | `/usr/local/lib/car-market/` | 회전·전송 실행 |
| Monitoring 수신 | `/var/spool/car-market/incoming/<source-id>/` | rsync staging |
| Monitoring 최종 보관 | `/var/log/car-market/archive/<source-id>/` | 역할별 gzip 보관 |
| Monitoring 격리 | `/var/spool/car-market/quarantine/<source-id>/` | 오류 파일 격리 |

## 5. EC2 적용 TODO

### 5.1 Monitoring EC2

- [ ] `logship` 전용 계정 생성
- [ ] staging, archive, quarantine 역할별 디렉터리 생성
- [ ] Monitoring 적재 스크립트와 환경파일 설치
- [ ] source별 SSH 공개키를 `logship` 계정에 등록
- [ ] 일별 적재 cron 등록
- [ ] 6개 source 디렉터리 권한과 빈 상태 적재 실행 확인

### 5.2 Collector / MySQL / MongoDB EC2 6대

- [ ] `resource.log` 실제 생성 경로와 서비스 계정 확인
- [ ] logrotate·전송 스크립트·환경파일 설치
- [ ] 서버별 `SOURCE_ID` 지정
- [ ] source별 전용 SSH key 생성 및 Monitoring host key 검증
- [ ] `logrotate -d`로 비파괴 설정 검사
- [ ] 1회 강제 회전·전송 smoke test
- [ ] 시간별 회전 cron 및 일별 전송 cron 등록

### 5.3 AWS 네트워크 및 보안

- [ ] source EC2 → Monitoring EC2 TCP 22 허용 여부 확인
- [ ] Monitoring Flask API용 TCP 5000 접근 정책 확인
- [ ] Network ACL의 응답 포트 범위 확인
- [ ] SSH host key 지문을 신뢰된 경로로 대조
- [ ] Monitoring 중앙 보관 기간과 백업 정책 결정

### 5.4 실시간 시스템 자원 모니터링

- [ ] `collect_metrics.sh`와 `metrics_loop.sh` 실제 배포
- [ ] `monitor.env`에 Monitoring API 주소와 실행 주기 설정
- [ ] `car-market-metrics.service` 등록 및 부팅 자동 시작 확인
- [ ] Flask `/api/metrics`, `/api/health` 실연동 확인
- [ ] Bastion Nginx Reverse Proxy와 Dashboard 접속 확인

## 6. 검증 범위와 제한 사항

이번 로컬 검증은 실제 AWS 접속 없이 fake rsync·fake logrotate를 사용해 파일 처리 계약을 확인했습니다.

따라서 다음 항목은 아직 “완료”가 아닙니다.

- 실제 EC2 SSH 인증과 rsync 전송
- Security Group / Network ACL 적용
- EC2 파일 권한과 `logship` 계정 권한
- 실제 cron과 systemd 실행
- Flask Dashboard의 실제 데이터 수신
- Monitoring 서버 디스크 보존 기간 운영

EC2 적용은 Monitoring 1대와 Collector 1대에서 end-to-end smoke test를 먼저 통과한 후, MySQL 2대와 MongoDB 3대로 확대 적용합니다.

## 7. 핵심 요약

현재 프로젝트는 로그 보관 자동화 모듈의 **로컬 구현·검증을 완료**했습니다. 목표는 6대 EC2의 시스템 자원 로그를 시간별로 압축하고, 일 1회 Monitoring 서버에 전송하여 서버 역할별로 분리 보관하는 것입니다.

실제 EC2 구성, 보안그룹 설정, cron/systemd 등록, 실시간 Dashboard 연동은 위 TODO 순서에 따라 차후 적용·검증합니다.
